"""Load and chunk the trusted corpus.

Corpus files are plain Markdown with a small header block::

    Title: Safe Cooking Temperatures
    Source: https://example.com/...
    Accessed: 2026-11-11
    Status: Summary — paraphrased from the source, not a verbatim quote.

    Body text...

Only the body is indexed. The header is metadata, kept with every chunk so
an answer can always cite where it came from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Document:
    doc_id: str
    title: str
    source: str
    accessed: str
    status: str
    body: str


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    source: str
    text: str


_HEADER_RE = re.compile(r"^(Title|Source|Accessed|Status):\s*(.*)$")


def parse_document(path: Path) -> Document:
    """Parse one corpus Markdown file into a Document."""
    lines = path.read_text(encoding="utf-8").splitlines()
    meta: dict[str, str] = {}
    body_lines: list[str] = []
    in_header = True
    for line in lines:
        m = _HEADER_RE.match(line)
        if in_header and m:
            meta[m.group(1).lower()] = m.group(2).strip()
            continue
        if in_header and line.strip() == "":
            in_header = False
            continue
        in_header = False
        body_lines.append(line)
    return Document(
        doc_id=path.stem,
        title=meta.get("title", path.stem),
        source=meta.get("source", "unknown"),
        accessed=meta.get("accessed", "unknown"),
        status=meta.get("status", "unknown"),
        body="\n".join(body_lines).strip(),
    )


def load_corpus(corpus_dir: Path) -> list[Document]:
    """Load every ``*.md`` file in ``corpus_dir``, sorted for determinism."""
    docs = [parse_document(p) for p in sorted(Path(corpus_dir).glob("*.md"))]
    if not docs:
        raise FileNotFoundError(f"No Markdown documents found in {corpus_dir}")
    return docs


def chunk_text(text: str, max_chars: int = 600, overlap: int = 100) -> list[str]:
    """Split text into overlapping chunks on sentence boundaries.

    Short texts return a single chunk. Longer texts are split at sentence
    ends so a chunk never starts mid-sentence unless a sentence itself is
    longer than ``max_chars``.
    """
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # A single over-long sentence is hard-split.
            while len(sentence) > max_chars:
                chunks.append(sentence[:max_chars])
                sentence = sentence[max_chars:]
            current = sentence
    if current:
        chunks.append(current)
    if overlap and len(chunks) > 1:
        overlapped: list[str] = [chunks[0]]
        for prev, chunk in zip(chunks, chunks[1:]):
            tail = prev[-overlap:] if len(prev) > overlap else prev
            overlapped.append(chunk if chunk.startswith(tail) else chunk)
        return overlapped
    return chunks


def chunk_documents(docs: list[Document]) -> list[Chunk]:
    """Chunk every document; chunk ids are ``<doc_id>-<n>``."""
    chunks: list[Chunk] = []
    for doc in docs:
        for i, text in enumerate(chunk_text(doc.body)):
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}-{i}",
                    doc_id=doc.doc_id,
                    title=doc.title,
                    source=doc.source,
                    text=text,
                )
            )
    return chunks
