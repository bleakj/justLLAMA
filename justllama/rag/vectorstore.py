"""ChromaDB-based local vector store for RAG."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot


class VectorStore(QObject):
    """Manages a ChromaDB collection for document embeddings.

    Signals:
        status_changed(str message)
    """

    status_changed = Signal(str)

    def __init__(self, store_path: str = "", collection_name: str = "justllama",
                 parent=None):
        super().__init__(parent)
        self._store_path = store_path or str(
            Path.home() / ".local" / "share" / "justllama" / "vectordb"
        )
        self._collection_name = collection_name
        self._client = None
        self._collection = None

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

        for i, chunk in enumerate(chunks):
            doc_id = f"chunk_{self._collection.count() + i}"
            ids.append(doc_id)
            documents.append(chunk["text"])
            # ChromaDB metadata values must be str/int/float/bool
            meta = {}
            for k, v in chunk.get("metadata", {}).items():
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

        count = self._collection.count()
        self.status_changed.emit(f"Vector store: {count} chunks total")
        return len(ids)

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
        """Delete all chunks from the collection."""
        self._ensure_client()
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self.status_changed.emit("Vector store cleared")

    @Slot(result=list)
    def list_collections(self) -> list[str]:
        """List all collections."""
        self._ensure_client()
        return [c.name for c in self._client.list_collections()]
