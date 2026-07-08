"""Tests for justllama.rag.vectorstore."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from PySide6.QtWidgets import QApplication

from justllama.rag.vectorstore import VectorStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------



@pytest.fixture()
def mock_chromadb():
    """Patch chromadb so no real database is touched.

    Returns (mock_module, mock_client, mock_collection).
    """
    mock_collection = MagicMock()
    mock_collection.count.return_value = 0
    mock_collection.name = "justllama"

    mock_client = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection

    mock_module = MagicMock()
    mock_module.PersistentClient.return_value = mock_client

    with patch.dict("sys.modules", {"chromadb": mock_module}):
        yield mock_module, mock_client, mock_collection


@pytest.fixture()
def store(qapp, tmp_path, mock_chromadb):
    """Fresh VectorStore with mocked chromadb."""
    return VectorStore(store_path=str(tmp_path / "vectordb"))


# ===================================================================
# _ensure_client tests
# ===================================================================

class TestEnsureClient:
    def test_lazy_initialization(self, store, mock_chromadb):
        """Client is None until _ensure_client is called."""
        assert store._client is None
        store._ensure_client()
        assert store._client is not None

    def test_creates_collection(self, store, mock_chromadb):
        """_ensure_client creates collection via get_or_create_collection."""
        _, mock_client, _ = mock_chromadb
        store._ensure_client()
        mock_client.get_or_create_collection.assert_called_once_with(
            name="justllama",
            metadata={"hnsw:space": "cosine"},
        )

    def test_reuses_existing_client(self, store, mock_chromadb):
        """Calling _ensure_client twice does not recreate the client."""
        mock_module, _, _ = mock_chromadb
        store._ensure_client()
        store._ensure_client()
        mock_module.PersistentClient.assert_called_once()

    def test_emits_status_signal(self, store, mock_chromadb):
        """_ensure_client emits status_changed with chunk count."""
        signals = []
        store.status_changed.connect(signals.append)
        store._ensure_client()
        assert len(signals) == 1
        assert "Vector store ready" in signals[0]
        assert "0 chunks" in signals[0]

    def test_handles_import_error(self, store):
        """When chromadb is missing, _ensure_client raises ImportError."""
        with patch.dict("sys.modules", {"chromadb": None}):
            with patch("builtins.__import__", side_effect=ImportError("no chromadb")):
                with pytest.raises(ImportError):
                    store._ensure_client()


# ===================================================================
# add_documents tests
# ===================================================================

class TestAddDocuments:
    def test_parses_chunks_json(self, store, mock_chromadb):
        """add_documents correctly parses JSON chunk list."""
        chunks = json.dumps([
            {"text": "Hello world", "metadata": {"source": "test.txt"}},
            {"text": "Second chunk", "metadata": {"page": 2}},
        ])
        count = store.add_documents(chunks)
        assert count == 2

    def test_calls_collection_add(self, store, mock_chromadb):
        """add_documents calls collection.add with ids, documents, metadatas."""
        _, _, mock_col = mock_chromadb
        mock_col.count.return_value = 0

        chunks = json.dumps([
            {"text": "Alpha", "src": "a"},
        ])
        store.add_documents(chunks)

        mock_col.add.assert_called_once()
        call_kwargs = mock_col.add.call_args[1]
        assert call_kwargs["ids"] == ["chunk_0"]
        assert call_kwargs["documents"] == ["Alpha"]
        assert call_kwargs["metadatas"] == [{"src": "a"}]

    def test_returns_count_of_added(self, store, mock_chromadb):
        """Return value is the number of chunks added."""
        _, _, mock_col = mock_chromadb
        mock_col.count.return_value = 0

        chunks = json.dumps([
            {"text": "A"},
            {"text": "B"},
            {"text": "C"},
        ])
        result = store.add_documents(chunks)
        assert result == 3

    def test_empty_input_returns_zero(self, store, mock_chromadb):
        """Empty chunk list returns 0 and does not call collection.add."""
        _, _, mock_col = mock_chromadb
        result = store.add_documents("[]")
        assert result == 0
        mock_col.add.assert_not_called()

    def test_emits_status_signal(self, store, mock_chromadb):
        """add_documents emits status_changed with total count."""
        store._ensure_client()  # pre-init so we capture only add_documents signal

        _, _, mock_col = mock_chromadb
        mock_col.count.return_value = 2

        signals = []
        store.status_changed.connect(signals.append)
        store.add_documents(json.dumps([{"text": "X"}]))
        assert len(signals) == 1
        assert "2 chunks total" in signals[0]

    def test_non_string_metadata_values_cast(self, store, mock_chromadb):
        """Metadata values that aren't str/int/float/bool are stringified."""
        _, _, mock_col = mock_chromadb
        mock_col.count.return_value = 0

        chunks = json.dumps([
            {"text": "test", "tags": ["a", "b"]},
        ])
        store.add_documents(chunks)
        call_kwargs = mock_col.add.call_args[1]
        assert call_kwargs["metadatas"] == [{"tags": "['a', 'b']"}]

    def test_chunk_ids_are_sequential(self, store, mock_chromadb):
        """Chunk IDs start from the current collection count."""
        _, _, mock_col = mock_chromadb
        mock_col.count.return_value = 5  # pretend 5 already exist

        chunks = json.dumps([
            {"text": "A"},
            {"text": "B"},
        ])
        store.add_documents(chunks)
        call_kwargs = mock_col.add.call_args[1]
        assert call_kwargs["ids"] == ["chunk_5", "chunk_6"]


# ===================================================================
# query tests
# ===================================================================

class TestQuery:
    def test_calls_collection_query(self, store, mock_chromadb):
        """query() calls collection.query with correct params."""
        _, _, mock_col = mock_chromadb
        mock_col.count.return_value = 3
        mock_col.query.return_value = {
            "ids": [["chunk_0"]],
            "documents": [["Result text"]],
            "metadatas": [[{"src": "test"}]],
            "distances": [[0.5]],
        }

        store.query("search term", n_results=1)
        mock_col.query.assert_called_once_with(
            query_texts=["search term"],
            n_results=1,
        )

    def test_returns_json_string(self, store, mock_chromadb):
        """query() returns a JSON string."""
        _, _, mock_col = mock_chromadb
        mock_col.count.return_value = 1
        mock_col.query.return_value = {
            "ids": [["c0"]],
            "documents": [["Hello"]],
            "metadatas": [[{"k": "v"}]],
            "distances": [[0.1]],
        }

        result = store.query("test")
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    def test_formats_results(self, store, mock_chromadb):
        """Each result contains id, text, metadata, distance keys."""
        _, _, mock_col = mock_chromadb
        mock_col.count.return_value = 1
        mock_col.query.return_value = {
            "ids": [["chunk_0"]],
            "documents": [["Found it"]],
            "metadatas": [[{"page": "1"}]],
            "distances": [[0.33]],
        }

        results = json.loads(store.query("test"))
        assert len(results) == 1
        r = results[0]
        assert r["id"] == "chunk_0"
        assert r["text"] == "Found it"
        assert r["metadata"] == {"page": "1"}
        assert r["distance"] == 0.33

    def test_empty_results(self, store, mock_chromadb):
        """When collection is empty, query returns '[]'."""
        _, _, mock_col = mock_chromadb
        mock_col.count.return_value = 0

        result = store.query("anything")
        assert result == "[]"

    def test_n_results_capped_at_count(self, store, mock_chromadb):
        """n_results is clamped to collection.count()."""
        _, _, mock_col = mock_chromadb
        mock_col.count.return_value = 2
        mock_col.query.return_value = {
            "ids": [["c0", "c1"]],
            "documents": [["A", "B"]],
            "metadatas": [[{}, {}]],
            "distances": [[0.1, 0.2]],
        }

        store.query("q", n_results=10)
        mock_col.query.assert_called_once_with(
            query_texts=["q"],
            n_results=2,
        )

    def test_results_without_distances(self, store, mock_chromadb):
        """When distances key is absent, distance is None."""
        _, _, mock_col = mock_chromadb
        mock_col.count.return_value = 1
        mock_col.query.return_value = {
            "ids": [["c0"]],
            "documents": [["X"]],
            "metadatas": [[{}]],
        }

        results = json.loads(store.query("q"))
        assert results[0]["distance"] is None


# ===================================================================
# count tests
# ===================================================================

class TestCount:
    def test_returns_collection_count(self, store, mock_chromadb):
        """count() delegates to collection.count()."""
        _, _, mock_col = mock_chromadb
        mock_col.count.return_value = 42
        assert store.count() == 42

    def test_returns_zero_when_not_initialized(self, store):
        """count() returns 0 when _ensure_client raises."""
        with patch.object(store, "_ensure_client", side_effect=RuntimeError("fail")):
            assert store.count() == 0


# ===================================================================
# clear tests
# ===================================================================

class TestClear:
    def test_deletes_and_recreates_collection(self, store, mock_chromadb):
        """clear() deletes the old collection and creates a new one."""
        _, mock_client, _ = mock_chromadb
        store._ensure_client()
        store.clear()
        mock_client.delete_collection.assert_called_once_with("justllama")
        assert mock_client.get_or_create_collection.call_count == 2  # init + clear

    def test_emits_status_signal(self, store, mock_chromadb):
        """clear() emits 'Vector store cleared'."""
        store._ensure_client()
        signals = []
        store.status_changed.connect(signals.append)
        store.clear()
        assert "Vector store cleared" in signals


# ===================================================================
# list_collections tests
# ===================================================================

class TestListCollections:
    def test_returns_collection_names(self, store, mock_chromadb):
        """list_collections() returns name strings from client."""
        _, mock_client, _ = mock_chromadb
        c1 = MagicMock()
        c1.name = "justllama"
        c2 = MagicMock()
        c2.name = "archive"
        mock_client.list_collections.return_value = [c1, c2]

        result = store.list_collections()
        assert result == ["justllama", "archive"]

    def test_empty_list(self, store, mock_chromadb):
        """list_collections() returns [] when no collections exist."""
        _, mock_client, _ = mock_chromadb
        mock_client.list_collections.return_value = []

        result = store.list_collections()
        assert result == []
