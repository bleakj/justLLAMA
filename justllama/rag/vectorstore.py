"""ChromaDB-based local vector store for RAG."""

from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot


class VectorStore(QObject):
    """Manages a ChromaDB collection for document embeddings.

    Signals:
        status_changed(str message)
    """

    status_changed = Signal(str)

    def __init__(self, store_path: str = "", collection_name: str = "justllama",
                 chunk_size: int = 512, chunk_overlap: int = 50, parent=None):
        super().__init__(parent)
        self._store_path = store_path or str(
            Path.home() / ".local" / "share" / "justllama" / "vectordb"
        )
        self._collection_name = collection_name
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._client = None
        self._collection = None
        self._retriever = None

    def set_retriever(self, retriever) -> None:
        """Link a Retriever so its BM25 keyword index stays in sync with
        ingestion. Optional — the store works without one."""
        self._retriever = retriever

    def _ensure_client(self):
        """Lazy-init ChromaDB client and collection."""
        if self._client is not None:
            return
        try:
            import chromadb
            Path(self._store_path).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self._store_path)
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self.status_changed.emit(
                f"Vector store ready: {self._collection.count()} chunks"
            )
        except ImportError:
            self.status_changed.emit(
                "ChromaDB not installed. Install with: pip install chromadb"
            )
            raise

    @Slot(str, result=int)
    def add_documents(self, chunks_json: str) -> int:
        """Add chunks to the vector store.

        Args:
            chunks_json: JSON string — list of {"text": str, "metadata": dict}.

        Returns:
            Number of chunks added.
        """
        import json

        self._ensure_client()
        chunks = json.loads(chunks_json)
        if not chunks:
            return 0

        ids = []
        documents = []
        metadatas = []

        for chunk in chunks:
            doc_id = f"chunk_{uuid.uuid4().hex}"
            ids.append(doc_id)
            documents.append(chunk["text"])
            # ChromaDB metadata values must be str/int/float/bool
            meta = {}
            for k, v in chunk.items():
                if k == "text":
                    continue
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v
                else:
                    meta[k] = str(v)
            metadatas.append(meta)

        self._collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        # Keep the retriever's keyword (BM25) fallback index in sync with the
        # embeddings so hybrid search still works if a vector query fails.
        if self._retriever is not None:
            try:
                self._retriever.add_chunks([
                    {"text": documents[i], "metadata": metadatas[i]}
                    for i in range(len(documents))
                ])
            except Exception:
                pass

        count = self._collection.count()
        self.status_changed.emit(f"Vector store: {count} chunks total")
        return len(ids)

    @Slot(str, result=bool)
    def remove_document(self, filename: str) -> bool:
        """Remove all chunks associated with a specific filename."""
        try:
            self._ensure_client()
            self._collection.delete(where={"filename": filename})
            # Drop the in-memory keyword corpus; it is rebuilt lazily from the
            # (now-updated) store on the next fallback search.
            if self._retriever is not None:
                self._retriever.clear_corpus()
            return True
        except Exception as e:
            self.status_changed.emit(f"Failed to remove document: {e}")
            return False

    @Slot(str, result=str)
    def ingest_document(self, file_path: str) -> str:
        """Ingest a file, chunk it, and add to the vector store.
        
        Returns a JSON string with stats or error.
        """
        import json
        import math
        from justllama.rag.ingestion import ingest_file
        
        try:
            path = Path(file_path)
            chunks = ingest_file(path, self._chunk_size, self._chunk_overlap)
            
            # add_documents expects JSON list of dicts
            chunks_data = [chunk.to_dict() for chunk in chunks]
            self.add_documents(json.dumps(chunks_data))
            
            size_bytes = path.stat().st_size
            if size_bytes == 0:
                formatted_size = "0B"
            else:
                size_name = ("B", "KB", "MB", "GB", "TB")
                i = int(math.floor(math.log(size_bytes, 1024)))
                p = math.pow(1024, i)
                s = round(size_bytes / p, 2)
                formatted_size = f"{s} {size_name[i]}"
                
            return json.dumps({
                "filename": path.name,
                "chunks": len(chunks),
                "size": formatted_size
            })
        except Exception as e:
            self.status_changed.emit(f"Ingestion failed: {e}")
            return json.dumps({"error": str(e)})

    @Slot(str, int, result=str)
    def query(self, query_text: str, n_results: int = 5) -> str:
        """Query the vector store for similar chunks.

        Args:
            query_text: Search query.
            n_results: Number of results to return.

        Returns:
            JSON string — list of {"id", "text", "metadata", "distance"}.
        """
        import json

        self._ensure_client()
        if self._collection.count() == 0:
            return "[]"

        results = self._collection.query(
            query_texts=[query_text],
            n_results=min(n_results, self._collection.count()),
        )

        output = []
        for i in range(len(results["ids"][0])):
            output.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i] if results.get("distances") else None,
            })

        return json.dumps(output)

    @Slot(result=str)
    def all_chunks(self) -> str:
        """Return every stored chunk as JSON — list of {"text", "metadata"}.

        Used by the retriever to (re)build its keyword fallback index from the
        authoritative store, e.g. for a vector DB that predates this session.
        """
        import json

        try:
            self._ensure_client()
            data = self._collection.get(include=["documents", "metadatas"])
        except Exception:
            return "[]"

        docs = data.get("documents") or []
        metas = data.get("metadatas") or []
        chunks = []
        for i, text in enumerate(docs):
            meta = metas[i] if i < len(metas) else {}
            chunks.append({"text": text, "metadata": meta or {}})
        return json.dumps(chunks)

    @Slot(result=int)
    def count(self) -> int:
        """Return total number of chunks in the store."""
        try:
            self._ensure_client()
            return self._collection.count()
        except Exception:
            return 0

    @Slot()
    def clear(self):
        """Delete all chunks from the collection.

        Re-creates the collection atomically (via get_or_create) before
        deleting the old one, so an in-flight query falls over to the new
        empty collection instead of hitting a missing-collection error.
        """
        self._ensure_client()
        try:
            new_collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            try:
                self._client.delete_collection(self._collection_name)
            except Exception:
                # If delete fails (e.g., first run) we still have a fresh
                # collection — keep going.
                pass
            self._collection = new_collection
            self.status_changed.emit("Vector store cleared")
            if self._retriever is not None:
                self._retriever.clear_corpus()
        except Exception as e:
            self.status_changed.emit(f"Clear failed: {e}")

