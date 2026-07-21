---
name: justllama-rag-pipeline
description: How justLLAMA's Retrieval-Augmented Generation works — document ingestion and chunking, the ChromaDB vector store, and the hybrid retriever with vector/BM25/substring fallbacks.
tags: [rag, retrieval, chromadb, embeddings, bm25, chunking, ingestion, hybrid-search]
audience: llm
---

# justLLAMA — RAG Pipeline

RAG lets the user ground chat responses in their own documents. It is **optional
and disabled by default** (`rag/enabled = false`) and requires the `[rag]` extra
(`chromadb`, `sentence-transformers`, `pymupdf`, `python-docx`, `rank_bm25`).
Three components make it up: **ingestion**, **vector store**, **retriever**.

## 1. Ingestion & chunking (`rag/ingestion.py`)

`ingest_file(path, chunk_size=512, chunk_overlap=50)` extracts text then chunks
it. Supported extensions (`SUPPORTED_EXTENSIONS`):

| Extension | Reader |
|-----------|--------|
| `.txt`, `.md`, `.rst` | plain UTF-8 read |
| `.pdf` | `pymupdf` (fitz) page-by-page text |
| `.docx` | `python-docx` paragraphs |

**Chunking algorithm** (`chunk_text`):
- Collapses runs of 3+ newlines, splits on paragraph boundaries (`\n\n`).
- Greedily packs paragraphs up to `chunk_size` **characters** (not tokens).
- A single paragraph larger than `chunk_size` is force-split on word boundaries.
- After chunking, a character-level **overlap** (default 50) from the previous
  chunk is prepended to each subsequent chunk, snapped to a word boundary, to
  preserve context across chunk edges.
- Each chunk carries metadata: `source` (full path), `filename`, `extension`,
  and `chunk_index`.

> Note: chunk sizing is measured in **characters**, so effective token counts
> vary by content. Defaults: `rag/chunk_size = 512`, `rag/chunk_overlap = 50`.

## 2. Vector store (`rag/vectorstore.py`, `VectorStore`)

A wrapper around a **persistent ChromaDB** collection named `justllama` using
**cosine** distance (`hnsw:space: cosine`). Storage path defaults to
`~/.local/share/justllama/vectordb`.

- **Lazy init**: the ChromaDB client/collection is created on first use
  (`_ensure_client`); if `chromadb` isn't installed it emits a status message
  and raises. Embeddings use ChromaDB's default embedding function unless
  configured otherwise.
- `ingest_document(file_path)` → chunks via ingestion, adds them, returns JSON
  stats `{filename, chunks, size}`.
- `add_documents(chunks_json)` → assigns each chunk a UUID id; coerces metadata
  values to str/int/float/bool (non-primitives stringified) since ChromaDB
  requires scalar metadata.
- `query(text, n_results=5)` → returns JSON list of `{id, text, metadata,
  distance}` (cosine distance).
- `remove_document(filename)` → deletes all chunks with that `filename`.
- `clear()` → atomically re-creates the collection (get_or_create the new one
  before deleting the old) so an in-flight query never hits a missing
  collection.
- `count()` → total chunks (0 on any error).
- Emits `status_changed(str)` for UI feedback.

## 3. Hybrid retriever (`rag/retriever.py`, `Retriever`)

`search(query, top_k=5)` returns a JSON list of `RetrievalResult`
(`{text, score, ...metadata}`) using a **tiered fallback**:

1. **Vector search** (preferred): if the vector store has >0 chunks, query it
   and convert cosine distance → similarity `score = 1.0 - distance`.
2. **BM25 keyword search** (fallback): if vector search is empty/unavailable and
   a BM25 corpus was loaded, tokenize with `\w+` and rank via `rank_bm25`'s
   `BM25Okapi`. Returns only positive-scoring hits.
3. **Substring search** (last resort): if `rank_bm25` isn't installed, rank by
   case-insensitive substring match density.

The BM25 corpus is managed separately from ChromaDB via `load_corpus(chunks)`,
`add_to_corpus(chunk_json)`, and `clear_corpus()`; the index is lazily rebuilt
and invalidated on corpus change. This design means **keyword retrieval still
works even without embeddings/ChromaDB**, embodying the graceful-degradation
philosophy.

## How RAG plugs into chat

When RAG is enabled, the UI/chat flow retrieves relevant chunks for the user's
query and injects them as context so the model can answer from the documents.
Retrieval is a plain read operation with no host side effects.

## Guidance for an operating model

- RAG context is grounding, not ground truth — cite/quote retrieved text rather
  than inventing details; if retrieval returns nothing, say so.
- Larger `top_k` and `chunk_size` consume more of the (default 4096-token)
  context window; be mindful when combined with memory injection.
- Scores are heuristic (vector similarity vs BM25 vs substring density) and are
  not directly comparable across the three tiers.
