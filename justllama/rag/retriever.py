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


    @Slot(str, result=bool)
    def add_to_corpus(self, chunk_json: str) -> bool:
        """Add a single chunk to the BM25 corpus.

        Args:
            chunk_json: JSON string — {"text": str, "metadata": dict}.
        """
        try:
            chunk = json.loads(chunk_json)
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
