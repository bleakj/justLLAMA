"""Hybrid search retriever combining vector similarity and keyword matching."""

from __future__ import annotations

import json
from dataclasses import dataclass

from PySide6.QtCore import QObject, Slot


@dataclass
class RetrievalResult:
    text: str
    score: float
    metadata: dict

    def to_dict(self) -> dict:
        return {"text": self.text, "score": self.score, **self.metadata}


class Retriever(QObject):
    """Hybrid retriever: vector similarity via ChromaDB + optional BM25 keyword fallback.

    Falls back to keyword search when the embedding model or ChromaDB
    is unavailable.
    """

    def __init__(self, vector_store=None, parent=None):
        super().__init__(parent)
        self._vector_store = vector_store
        self._bm25_index: BM25Okapi | None = None
        self._bm25_corpus: list[dict] = []

    def _rebuild_bm25_index(self):
        from rank_bm25 import BM25Okapi
        import re
        tokenized_corpus = [
            re.findall(r'\w+', doc["text"].lower())
            for doc in self._bm25_corpus
        ]
        self._bm25_index = BM25Okapi(tokenized_corpus)


    @Slot(str, int, result=str)
    def search(self, query: str, top_k: int = 5) -> str:
        """Search for relevant chunks.

        Tries vector search first; falls back to BM25 keyword search
        if vector store is empty or unavailable.

        Args:
            query: Search query string.
            top_k: Number of results to return.

        Returns:
            JSON string — list of RetrievalResult dicts.
        """
        results = []

        # Try vector search
        if self._vector_store is not None:
            try:
                count = self._vector_store.count()
                if count > 0:
                    raw = self._vector_store.query(query, top_k)
                    items = json.loads(raw)
                    for item in items:
                        # Convert cosine distance to similarity score
                        distance = item.get("distance", 1.0)
                        score = 1.0 - (distance if distance is not None else 1.0)
                        results.append(RetrievalResult(
                            text=item["text"],
                            score=score,
                            metadata=item.get("metadata", {}),
                        ))
                    return json.dumps([r.to_dict() for r in results])
            except Exception:
                pass  # Fall through to BM25

        # BM25 fallback
        results = self._bm25_search(query, top_k)
        return json.dumps([r.to_dict() for r in results])
    def _bm25_search(self, query: str, top_k: int) -> list[RetrievalResult]:
        """Keyword-based BM25 search, with a plain substring fallback.

        Falls back to substring matching when the optional ``rank_bm25``
        package isn't installed so keyword search still produces hits.
        """
        if not self._bm25_corpus:
            # Cold start: nothing was ingested this session but the vector
            # store may already hold chunks (e.g. a DB from a previous run).
            # Pull them so keyword fallback works over the same documents.
            self._sync_corpus_from_store()
        if not self._bm25_corpus:
            return []

        if self._bm25_index is None:
            try:
                self._rebuild_bm25_index()
            except ImportError:
                # rank_bm25 isn't installed; fall back to plain keyword
                # matching so a populated corpus doesn't return empty.
                return self._substring_search(query, top_k)

        import re
        tokenized_query = re.findall(r'\w+', query.lower())
        scores = self._bm25_index.get_scores(tokenized_query)

        # Get top-k indices
        indexed = sorted(enumerate(scores), key=lambda x: -x[1])[:top_k]
        results = []
        for idx, score in indexed:
            if score > 0:
                doc = self._bm25_corpus[idx]
                results.append(RetrievalResult(
                    text=doc["text"],
                    score=float(score),
                    metadata=doc.get("metadata", {}),
                ))
        return results

    def _substring_search(self, query: str, top_k: int) -> list[RetrievalResult]:
        """Naive case-insensitive substring ranking — last-resort fallback."""
        q = query.lower().strip()
        if not q:
            return []

        scored = []
        for doc in self._bm25_corpus:
            text = doc.get("text", "")
            lower = text.lower()
            count = lower.count(q)
            if count > 0:
                # Reward density: matches per char-of-text, biased upwards.
                density = count / max(len(lower), 1)
                scored.append((density, doc))
        scored.sort(key=lambda x: -x[0])
        return [
            RetrievalResult(
                text=d["text"],
                score=float(s),
                metadata=d.get("metadata", {}),
            )
            for s, d in scored[:top_k]
        ]


    def load_corpus(self, chunks: list[dict]):
        """Load chunks into the BM25 index for keyword search fallback.

        Args:
            chunks: List of {"text": str, "metadata": dict}.
        """
        self._bm25_corpus = chunks
        self._bm25_index = None  # invalidate cache

    def add_chunks(self, chunks: list[dict]) -> None:
        """Append already-parsed chunks to the BM25 corpus.

        Called by the vector store as documents are ingested so the keyword
        fallback index stays in sync with the embeddings.
        """
        for chunk in chunks:
            if isinstance(chunk, dict) and isinstance(chunk.get("text"), str):
                self._bm25_corpus.append(chunk)
        self._bm25_index = None  # invalidate cache

    def _sync_corpus_from_store(self) -> bool:
        """Populate the BM25 corpus from the vector store's contents.

        Cold-start fallback so keyword search works over a pre-existing vector
        DB even when nothing was ingested this session. Only called when the
        in-memory corpus is empty, so it never overwrites chunks added via
        ``load_corpus`` / ``add_to_corpus`` / ``add_chunks``.
        """
        if self._vector_store is None:
            return False
        all_chunks = getattr(self._vector_store, "all_chunks", None)
        if not callable(all_chunks):
            return False
        try:
            chunks = json.loads(all_chunks())
        except Exception:
            return False
        if chunks:
            self._bm25_corpus = chunks
            self._bm25_index = None  # invalidate cache
            return True
        return False


    @Slot(str, result=bool)
    def add_to_corpus(self, chunk_json: str) -> bool:
        """Add a single chunk to the BM25 corpus.

        Args:
            chunk_json: JSON string — {"text": str, "metadata": dict}.
        """
        try:
            chunk = json.loads(chunk_json)
            if not isinstance(chunk, dict) or not isinstance(chunk.get("text"), str):
                return False
            self._bm25_corpus.append(chunk)
            self._bm25_index = None  # invalidate cache
            return True
        except (json.JSONDecodeError, KeyError):
            return False


    @Slot()
    def clear_corpus(self):
        """Clear the BM25 corpus."""
        self._bm25_corpus.clear()
        self._bm25_index = None

    # ------------------------------------------------------------------
    # LLM-based reranking (WS3)
    # ------------------------------------------------------------------
    # NOTE: rerank() and retrieve_for_chat() make a blocking network call and
    # MUST run off the UI thread. They are invoked from ChatRunner (a QThread),
    # never directly from QML, so the Qt/QML event loop is never blocked.

    @staticmethod
    def _parse_index_list(content: str, n: int) -> list[int]:
        """Parse a model's JSON index array, keeping valid unique indices and
        appending any missing ones so the ordering stays complete."""
        import re
        match = re.search(r"\[[^\]]*\]", content or "")
        if not match:
            return []
        try:
            raw = json.loads(match.group(0))
        except Exception:
            return []
        if not isinstance(raw, list):
            return []
        seen: set[int] = set()
        order: list[int] = []
        for x in raw:
            try:
                idx = int(x)
            except (ValueError, TypeError):
                continue
            if 0 <= idx < n and idx not in seen:
                seen.add(idx)
                order.append(idx)
        for i in range(n):
            if i not in seen:
                order.append(i)
        return order

    def rerank(self, query: str, candidates: list[dict], top_k: int = 5, *,
               model: str = "default", port: int = 8080,
               timeout: float = 20) -> list[dict]:
        """Listwise LLM rerank of candidate result dicts.

        Asks the configured chat/cloud model to order the candidate passages by
        relevance and returns them reordered and truncated to ``top_k``. On any
        failure or timeout the original order (truncated) is returned unchanged.
        """
        if not candidates:
            return []
        n = len(candidates)
        if n == 1:
            return candidates[:top_k]
        try:
            from justllama.server.client import LlamaClient
            client = LlamaClient(port=port)
            listing = []
            for i, c in enumerate(candidates):
                text = (c.get("text") or "")[:500]
                listing.append(f"[{i}] {text}")
            prompt = (
                "You are a search result reranker. Given a query and a numbered "
                "list of passages, return the passage indices ordered from most "
                "to least relevant to the query. Respond ONLY with a JSON array "
                f"of integers, e.g. [2,0,1]. Use only indices 0..{n - 1}, no "
                "duplicates.\n\n"
                f"Query: {query}\n\nPassages:\n" + "\n".join(listing)
            )
            resp = client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=model, temperature=0.0, max_tokens=128,
                stream=False, timeout=timeout,
            )
            content = ""
            if isinstance(resp, dict):
                choices = resp.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "") or ""
            order = self._parse_index_list(content, n)
            if not order:
                return candidates[:top_k]
            reranked = [candidates[i] for i in order]
            return reranked[:top_k]
        except Exception:
            return candidates[:top_k]

    def retrieve_for_chat(self, query: str, top_k: int = 3, *,
                          rerank_enabled: bool = False, rerank_top_n: int = 20,
                          model: str = "default", port: int = 8080) -> list[dict]:
        """Retrieve (and optionally LLM-rerank) chunks for a chat turn.

        Runs the vector/BM25 search, then, when reranking is enabled, fetches a
        wider candidate set (``rerank_top_n``) and reorders it via ``rerank``
        before truncating to ``top_k``. Intended to be called from a background
        thread; never the UI thread.
        """
        fetch_k = rerank_top_n if rerank_enabled else top_k
        try:
            candidates = json.loads(self.search(query, fetch_k))
        except Exception:
            candidates = []
        if not candidates:
            return []
        if rerank_enabled:
            candidates = self.rerank(query, candidates, top_k=top_k,
                                     model=model, port=port)
        return candidates[:top_k]
