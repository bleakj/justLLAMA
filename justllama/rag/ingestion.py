"""Document chunking pipeline for RAG ingestion."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"text": self.text, **self.metadata}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_pdf(path: Path) -> str:
    """Extract text from PDF using pymupdf (fitz)."""
    try:
        import fitz
        doc = fitz.open(str(path))
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        return "\n\n".join(pages)
    except ImportError:
        raise ImportError(
            "pymupdf is required for PDF support. "
            "Install with: pip install pymupdf"
        )


def _read_docx(path: Path) -> str:
    """Extract text from DOCX using python-docx."""
    try:
        import docx
        doc = docx.Document(str(path))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        raise ImportError(
            "python-docx is required for DOCX support. "
            "Install with: pip install python-docx"
        )


_READERS = {
    ".txt": _read_text,
    ".md": _read_text,
    ".rst": _read_text,
    ".pdf": _read_pdf,
    ".docx": _read_docx,
}

SUPPORTED_EXTENSIONS = set(_READERS.keys())


def extract_text(path: Path) -> str:
    """Extract raw text from a supported document."""
    ext = path.suffix.lower()
    reader = _READERS.get(ext)
    if reader is None:
        raise ValueError(
            f"Unsupported file type: {ext}. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    return reader(path)


def chunk_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    metadata: dict | None = None,
) -> list[Chunk]:
    """Split text into overlapping chunks.

    Args:
        text: Raw document text.
        chunk_size: Target chunk size in characters.
        chunk_overlap: Overlap between consecutive chunks.
        metadata: Base metadata attached to every chunk.

    Returns:
        List of Chunk objects.
    """
    if chunk_overlap >= chunk_size:
        chunk_overlap = chunk_size // 2
    if not text or not text.strip():
        return []

    meta = metadata or {}
    chunks = []

    # Normalize whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Split on paragraph boundaries first
    paragraphs = text.split('\n\n')

    current = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(Chunk(text=current, metadata={**meta, "chunk_index": len(chunks)}))
            # If single paragraph exceeds chunk_size, force-split it
            if len(para) > chunk_size:
                words = para.split()
                current = ""
                for word in words:
                    if len(current) + len(word) + 1 <= chunk_size:
                        current = f"{current} {word}" if current else word
                    else:
                        if current:
                            chunks.append(Chunk(text=current, metadata={**meta, "chunk_index": len(chunks)}))
                        current = word
            else:
                current = para

    if current:
        chunks.append(Chunk(text=current, metadata={**meta, "chunk_index": len(chunks)}))

    # Add overlap between consecutive chunks
    if chunk_overlap > 0 and len(chunks) > 1:
        for i in range(1, len(chunks)):
            prev_text = chunks[i - 1].text
            overlap = prev_text[-chunk_overlap:]
            # Try to break at a word boundary
            first_space = overlap.find(' ')
            if 0 < first_space < len(overlap) - 1:
                overlap = overlap[first_space + 1:]
            merged = overlap + chunks[i].text
            # Trim to word boundary if merged exceeds chunk_size
            if len(merged) > chunk_size:
                trimmed = merged[:chunk_size]
                last_space = trimmed.rfind(' ')
                if last_space > 0:
                    merged = trimmed[:last_space]
                else:
                    merged = trimmed
            chunks[i] = Chunk(
                text=merged,
                metadata={**chunks[i].metadata, "chunk_index": i}
            )

    return chunks


def ingest_file(
    path: str | Path,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> list[Chunk]:
    """Extract text from a file and chunk it.

    Args:
        path: Path to document.
        chunk_size: Target chunk size in characters.
        chunk_overlap: Overlap between consecutive chunks.

    Returns:
        List of Chunk objects with source metadata.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")

    text = extract_text(p)
    if not text.strip():
        return []

    metadata = {
        "source": str(p),
        "filename": p.name,
        "extension": p.suffix.lower(),
    }

    return chunk_text(text, chunk_size, chunk_overlap, metadata)
