"""
Chunker for The Unofficial Guide.

Splits the cleaned .txt documents in ../documents/ into overlapping,
character-based chunks suitable for embedding.

Strategy (per planning.md):
  - Character-based splitting. The corpus mixes long guides (Niche, US News)
    with short, variable-length reviews (RateMyProfessors, Reddit), so a fixed
    *token* window fits poorly; a character window with sentence-aware
    boundaries keeps reviews intact while still capping long guides.
  - CHUNK_SIZE characters per chunk with CHUNK_OVERLAP characters of overlap so
    that information split across a boundary (e.g. a professor's name in one
    sentence and the opinion in the next) is not lost.
  - Splits prefer paragraph and sentence boundaries before falling back to a
    hard character cut, so chunks stay readable.

Each chunk carries metadata (source file + source URL) for attribution in the
RAG pipeline.

Run standalone to preview chunk stats:
    python chunker.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

DOCUMENTS_DIR = Path(__file__).resolve().parent.parent / "documents"

CHUNK_SIZE = 800          # characters per chunk
CHUNK_OVERLAP = 150       # characters shared between consecutive chunks
MIN_CHUNK_CHARS = 50      # discard tiny fragments

# Repetitive site chrome that appears in browser-rendered text but carries no
# review value. Matched case-insensitively as substrings and stripped out.
BOILERPLATE_PHRASES = (
    "skip to main content",
    "sign up log in",
    "log in sign up",
    "expand user menu",
    "professors log in sign up help",
    "rate compare",
    "create post",
    "view more",
    "promoted",
    "advertisement",
    "cookie",
    "accept all",
)


def _strip_boilerplate(text: str) -> str:
    """Remove repeated site-chrome phrases from rendered page text."""
    lowered_phrases = [p.lower() for p in BOILERPLATE_PHRASES]
    out_lines = []
    for line in text.splitlines():
        low = line.lower()
        # Drop a line only if it is largely boilerplate (short nav fragments).
        if any(p in low for p in lowered_phrases) and len(line) < 80:
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


# The RateMyProfessors professor file concatenates one block per professor, each
# starting with this marker. We split on it so each professor's reviews can be
# tagged with the professor's name + department on every chunk (otherwise the
# department header is lost after the first 800-char chunk, which caused the
# model to misattribute professors to the wrong department).
RMP_PROF_FILE = "ratemyprofessors_professors_ccsu.txt"
_PROF_BLOCK_RE = re.compile(r"(?=Professors Log In Sign Up Help )")
_PROF_DEPT_RE = re.compile(
    r"Professor in the (.+?) department at Central Connecticut State University"
)
_PROF_NAME_RE = re.compile(
    r"([A-Z][\w.'-]+(?: [A-Z][\w.'-]+)*) Professor in the .+? department"
)


def _split_professor_blocks(body: str) -> list[tuple[str, str, str]]:
    """Split the RMP professors blob into (name, department, text) tuples."""
    blocks: list[tuple[str, str, str]] = []
    for raw in _PROF_BLOCK_RE.split(body):
        raw = raw.strip()
        if len(raw) < 40:
            continue
        dept_m = _PROF_DEPT_RE.search(raw)
        name_m = _PROF_NAME_RE.search(raw)
        department = dept_m.group(1).strip() if dept_m else ""
        name = name_m.group(1).strip() if name_m else ""
        blocks.append((name, department, raw))
    return blocks


def _chunk_professor_file(path: Path, source_url: str, body: str) -> list[Chunk]:
    """Chunk the professors file, tagging every chunk with name + department."""
    chunks: list[Chunk] = []
    idx = 0
    for name, department, block in _split_professor_blocks(body):
        block = _strip_boilerplate(block)
        # A clear header prepended to every chunk so the professor's identity and
        # department travel with each piece of their reviews.
        if name and department:
            header = f"Professor: {name} ({department} department at CCSU)\n"
        elif name:
            header = f"Professor: {name} (CCSU)\n"
        else:
            header = ""
        for piece in chunk_text(block):
            chunks.append(Chunk(
                text=header + piece,
                source_file=path.name,
                source_url=source_url,
                index=idx,
                metadata={
                    "source_file": path.name,
                    "source_url": source_url,
                    "chunk_index": idx,
                    "professor": name,
                    "department": department,
                },
            ))
            idx += 1
    return chunks



@dataclass
class Chunk:
    text: str
    source_file: str
    source_url: str
    index: int
    metadata: dict = field(default_factory=dict)


def _read_document(path: Path) -> tuple[str, str]:
    """Return (source_url, body) for a scraped document.

    Scraped files start with a `SOURCE: <url>` header followed by a separator
    line of `=`; this strips that header so it is not embedded into chunks.
    """
    raw = path.read_text(encoding="utf-8")
    source_url = ""
    lines = raw.splitlines()
    if lines and lines[0].startswith("SOURCE:"):
        source_url = lines[0].replace("SOURCE:", "").strip()
        # Drop the header line and the following separator/blank lines.
        body_lines = lines[1:]
        while body_lines and (set(body_lines[0].strip()) <= {"="}
                              or not body_lines[0].strip()):
            body_lines.pop(0)
        body = "\n".join(body_lines)
    else:
        body = raw
    return source_url, body


def _split_into_segments(text: str) -> list[str]:
    """Break text into paragraph/sentence segments used as packing units."""
    segments: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        # Further split very long paragraphs on sentence boundaries.
        if len(paragraph) > CHUNK_SIZE:
            sentences = re.split(r"(?<=[.!?])\s+", paragraph)
            segments.extend(s.strip() for s in sentences if s.strip())
        else:
            segments.append(paragraph)
    return segments


def chunk_text(text: str) -> list[str]:
    """Pack segments into ~CHUNK_SIZE character chunks with overlap."""
    segments = _split_into_segments(text)
    chunks: list[str] = []
    current = ""

    for seg in segments:
        # A single segment longer than CHUNK_SIZE is hard-split.
        if len(seg) > CHUNK_SIZE:
            if current:
                chunks.append(current.strip())
                current = ""
            for i in range(0, len(seg), CHUNK_SIZE - CHUNK_OVERLAP):
                chunks.append(seg[i:i + CHUNK_SIZE].strip())
            continue

        if not current:
            current = seg
        elif len(current) + 1 + len(seg) <= CHUNK_SIZE:
            current = f"{current}\n{seg}"
        else:
            chunks.append(current.strip())
            # Start the next chunk with a tail-overlap of the previous one.
            overlap_tail = current[-CHUNK_OVERLAP:] if CHUNK_OVERLAP else ""
            current = f"{overlap_tail}\n{seg}".strip()

    if current.strip():
        chunks.append(current.strip())

    return [c for c in chunks if len(c) >= MIN_CHUNK_CHARS]


def chunk_documents(documents_dir: Path = DOCUMENTS_DIR) -> list[Chunk]:
    """Chunk every .txt document in the documents directory."""
    all_chunks: list[Chunk] = []
    txt_files = sorted(documents_dir.glob("*.txt"))
    if not txt_files:
        raise FileNotFoundError(
            f"No .txt documents found in {documents_dir}. Run scraper.py first."
        )

    for path in txt_files:
        source_url, body = _read_document(path)
        # The professors file needs per-professor handling so the department
        # header is not lost across chunk boundaries.
        if path.name == RMP_PROF_FILE:
            all_chunks.extend(_chunk_professor_file(path, source_url, body))
            continue
        body = _strip_boilerplate(body)
        pieces = chunk_text(body)
        for i, piece in enumerate(pieces):
            all_chunks.append(Chunk(
                text=piece,
                source_file=path.name,
                source_url=source_url,
                index=i,
                metadata={
                    "source_file": path.name,
                    "source_url": source_url,
                    "chunk_index": i,
                },
            ))
    return all_chunks


def main() -> None:
    chunks = chunk_documents()
    by_file: dict[str, int] = {}
    for c in chunks:
        by_file[c.source_file] = by_file.get(c.source_file, 0) + 1

    print(f"Total chunks: {len(chunks)}")
    print(f"Chunk size: {CHUNK_SIZE} chars, overlap: {CHUNK_OVERLAP} chars\n")
    for fname, count in sorted(by_file.items()):
        print(f"  {fname}: {count} chunks")

    if chunks:
        avg = sum(len(c.text) for c in chunks) / len(chunks)
        print(f"\nAverage chunk length: {avg:.0f} chars")
        print("\n--- sample chunk ---")
        print(chunks[0].text[:400])


if __name__ == "__main__":
    main()
