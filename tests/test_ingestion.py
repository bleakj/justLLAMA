"""Tests for justllama.rag.ingestion — document chunking pipeline.

All tests are self-contained. No server, GPU, or network needed.
"""

from pathlib import Path

import pytest

from justllama.rag.ingestion import (
    Chunk,
    SUPPORTED_EXTENSIONS,
    chunk_text,
    extract_text,
    ingest_file,
)


# ---------------------------------------------------------------------------
# Chunk dataclass
# ---------------------------------------------------------------------------


class TestChunkDataclass:
    def test_to_dict_returns_text_key(self):
        c = Chunk(text="hello")
        d = c.to_dict()
        assert d["text"] == "hello"

    def test_to_dict_merges_metadata(self):
        c = Chunk(text="x", metadata={"source": "a.txt", "chunk_index": 0})
        d = c.to_dict()
        assert d == {"text": "x", "source": "a.txt", "chunk_index": 0}

    def test_to_dict_empty_metadata(self):
        c = Chunk(text="y")
        assert c.to_dict() == {"text": "y"}

    def test_default_metadata_is_empty_dict(self):
        c = Chunk(text="z")
        assert c.metadata == {}


# ---------------------------------------------------------------------------
# SUPPORTED_EXTENSIONS
# ---------------------------------------------------------------------------


class TestSupportedExtensions:
    def test_contains_txt(self):
        assert ".txt" in SUPPORTED_EXTENSIONS

    def test_contains_md(self):
        assert ".md" in SUPPORTED_EXTENSIONS

    def test_contains_pdf(self):
        assert ".pdf" in SUPPORTED_EXTENSIONS

    def test_contains_docx(self):
        assert ".docx" in SUPPORTED_EXTENSIONS

    def test_is_a_set(self):
        assert isinstance(SUPPORTED_EXTENSIONS, set)


# ---------------------------------------------------------------------------
# extract_text
# ---------------------------------------------------------------------------


class TestExtractText:
    def test_reads_txt_file(self, tmp_path):
        f = tmp_path / "sample.txt"
        f.write_text("Hello world")
        assert extract_text(f) == "Hello world"

    def test_reads_md_file(self, tmp_path):
        f = tmp_path / "notes.md"
        f.write_text("# Title\n\nBody text")
        assert extract_text(f) == "# Title\n\nBody text"

    def test_txt_preserves_newlines(self, tmp_path):
        content = "line1\nline2\n\nline3"
        f = tmp_path / "multi.txt"
        f.write_text(content)
        assert extract_text(f) == content

    def test_unsupported_extension_raises(self, tmp_path):
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG\r\n")
        with pytest.raises(ValueError, match="Unsupported file type"):
            extract_text(f)

    def test_unsupported_extension_lists_valid_types(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("a,b,c")
        with pytest.raises(ValueError) as exc_info:
            extract_text(f)
        msg = str(exc_info.value)
        assert ".txt" in msg
        assert ".md" in msg


# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------


class TestChunkText:
    def test_empty_text_returns_empty(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []
        assert chunk_text("\n\n\n") == []

    def test_short_text_returns_single_chunk(self):
        chunks = chunk_text("Hello world", chunk_size=512)
        assert len(chunks) == 1
        assert chunks[0].text == "Hello world"

    def test_splits_into_chunks_of_specified_size(self):
        # Create text that will exceed one chunk
        text = "word " * 200  # ~1000 chars
        chunks = chunk_text(text, chunk_size=200)
        assert len(chunks) > 1
        for c in chunks:
            # Chunks should not drastically exceed the target size
            assert len(c.text) <= 300  # generous headroom for paragraph merging

    def test_chunks_have_chunk_index_metadata(self):
        chunks = chunk_text("a\n\nb\n\nc\n\nd", chunk_size=10)
        for i, c in enumerate(chunks):
            assert c.metadata["chunk_index"] == i

    def test_base_metadata_propagated(self):
        meta = {"source": "test.txt", "filename": "test.txt"}
        chunks = chunk_text("one two three", chunk_size=512, metadata=meta)
        assert len(chunks) >= 1
        for c in chunks:
            assert c.metadata["source"] == "test.txt"
            assert c.metadata["filename"] == "test.txt"

    def test_word_boundaries_preserved_no_mid_word_split(self):
        # Build text long enough to force splitting, with words that must stay whole
        words = [f"word{i:03d}" for i in range(200)]
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=200)
        assert len(chunks) > 1
        for c in chunks:
            # Every chunk should start/end at word boundaries
            assert not c.text.startswith(" ")
            assert not c.text.endswith(" ")
            # No word should be truncated (all words in chunks are complete)
            for word in c.text.split():
                assert word.startswith("word") or word.startswith("word")

    def test_paragraphs_are_kept_together_when_possible(self):
        # Two paragraphs that fit within chunk_size together
        para1 = "A" * 50
        para2 = "B" * 50
        text = f"{para1}\n\n{para2}"
        chunks = chunk_text(text, chunk_size=200)
        assert len(chunks) == 1
        assert para1 in chunks[0].text
        assert para2 in chunks[0].text

    def test_large_paragraph_force_splits_on_words(self):
        # Single paragraph exceeding chunk_size
        words = [f"w{i}" for i in range(100)]
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=100)
        assert len(chunks) > 1
        for c in chunks:
            assert len(c.text) <= 150  # generous margin

    def test_triple_newlines_normalized_to_double(self):
        text = "AAA\n\n\n\nBBB"
        chunks = chunk_text(text, chunk_size=512)
        assert len(chunks) == 1
        # Normalized: triple+ newlines become double
        assert "\n\n\n" not in chunks[0].text

    def test_no_metadata_uses_empty_dict(self):
        chunks = chunk_text("hello world")
        assert chunks[0].metadata == {"chunk_index": 0}

    def test_chunk_index_increments_across_chunks(self):
        # Force multiple chunks
        paragraphs = [f"Paragraph {i} content here." for i in range(10)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, chunk_size=60)
        indices = [c.metadata["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))


# ---------------------------------------------------------------------------
# ingest_file
# ---------------------------------------------------------------------------


class TestIngestFile:
    def test_returns_list_of_chunk_objects(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Some content here for testing.")
        result = ingest_file(f)
        assert isinstance(result, list)
        assert all(isinstance(c, Chunk) for c in result)

    def test_metadata_includes_filename(self, tmp_path):
        f = tmp_path / "myfile.txt"
        f.write_text("Content to ingest.")
        chunks = ingest_file(f)
        assert len(chunks) >= 1
        for c in chunks:
            assert c.metadata["filename"] == "myfile.txt"

    def test_metadata_includes_source_path(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Some text.")
        chunks = ingest_file(f)
        for c in chunks:
            assert c.metadata["source"] == str(f)

    def test_metadata_includes_extension(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("Notes content.")
        chunks = ingest_file(f)
        for c in chunks:
            assert c.metadata["extension"] == ".txt"

    def test_metadata_includes_chunk_index(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("A\n\nB\n\nC\n\nD\n\nE")
        chunks = ingest_file(f, chunk_size=5)
        for i, c in enumerate(chunks):
            assert c.metadata["chunk_index"] == i

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="File not found"):
            ingest_file(tmp_path / "nonexistent.txt")

    def test_works_with_string_path(self, tmp_path):
        f = tmp_path / "str_path.txt"
        f.write_text("String path test.")
        result = ingest_file(str(f))
        assert len(result) >= 1

    def test_md_file_ingested(self, tmp_path):
        f = tmp_path / "readme.md"
        f.write_text("# Heading\n\nSome markdown body text.")
        chunks = ingest_file(f)
        assert len(chunks) >= 1
        assert chunks[0].metadata["extension"] == ".md"

    def test_empty_file_returns_empty(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        result = ingest_file(f)
        assert result == []

    def test_custom_chunk_size(self, tmp_path):
        f = tmp_path / "big.txt"
        words = [f"word{i}" for i in range(200)]
        f.write_text(" ".join(words))
        chunks = ingest_file(f, chunk_size=100)
        assert len(chunks) > 1
