import hashlib
import re
from typing import Any

from app.services.ingestion.parsers import normalize_text


class ChunkItem:
    def __init__(
        self,
        chunk_index: int,
        content: str,
        chunk_hash: str,
        title: str | None = None,
        page: int | None = None,
        meta_info: dict[str, Any] | None = None,
    ):
        self.chunk_index = chunk_index
        self.content = content
        self.chunk_hash = chunk_hash
        self.title = title
        self.page = page
        self.meta_info = meta_info or {}


def compute_hash(text: str) -> str:
    """Compute deterministic SHA-256 hash of normalized text."""
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_file_hash(content_bytes: bytes) -> str:
    """Compute SHA-256 hash of file content bytes."""
    return hashlib.sha256(content_bytes).hexdigest()


class MarkdownChunker:
    """Structure-aware chunker splitting on markdown headings and paragraphs.

    Target chunk size: up to ~1000 tokens (4000 chars) so a whole course or person stays together.
    Overlap: 10-15% (~250-400 chars).
    """

    def __init__(
        self,
        min_chars: int = 400,
        max_chars: int = 4000,
        overlap_chars: int = 350,
    ):
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def chunk_document(
        self,
        text: str,
        document_title: str,
    ) -> list[ChunkItem]:
        normalized_doc = normalize_text(text)
        if not normalized_doc:
            return []

        sections = self._split_into_units(normalized_doc, document_title)

        chunks: list[ChunkItem] = []
        chunk_idx = 0

        for section_title, section_text, unit_heading in sections:
            if len(section_text) <= self.max_chars:
                if len(section_text.strip()) >= 50:
                    ch_hash = compute_hash(section_text)
                    chunks.append(
                        ChunkItem(
                            chunk_index=chunk_idx,
                            content=section_text.strip(),
                            chunk_hash=ch_hash,
                            title=section_title,
                        )
                    )
                    chunk_idx += 1
            else:
                # Sub-split large sections with overlap
                sub_chunks = self._split_large_section(section_text)
                for sub_text in sub_chunks:
                    if unit_heading and not sub_text.startswith(unit_heading):
                        sub_text = f"{unit_heading}\n\n{sub_text}"
                    if len(sub_text.strip()) >= 50:
                        ch_hash = compute_hash(sub_text)
                        chunks.append(
                            ChunkItem(
                                chunk_index=chunk_idx,
                                content=sub_text.strip(),
                                chunk_hash=ch_hash,
                                title=section_title,
                            )
                        )
                        chunk_idx += 1

        return chunks

    def _split_into_units(self, text: str, default_title: str) -> list[tuple[str, str, str]]:
        """Keep one logical unit (a course, a person) in one chunk whenever it fits.

        The unit heading level is the shallowest level (1 to 3) that repeats. A unit that
        fits in max_chars stays whole, so facts like a prerequisite are never stored apart
        from the name of the thing they describe. A larger unit is split by its sub-headings
        and every piece repeats the unit heading for context.
        """
        level = self._unit_level(text)
        if level is None:
            return [(t, b, "") for t, b in self._split_by_headers(text, default_title)]

        units = self._split_by_headers(text, default_title, max_level=level)
        sections: list[tuple[str, str, str]] = []
        for unit_title, unit_text in units:
            if len(unit_text) <= self.max_chars or not unit_text.startswith("#"):
                sections.append((unit_title, unit_text, ""))
                continue
            heading, _, body = unit_text.partition("\n")
            # Pack consecutive sub-sections so a big unit becomes a few chunks, not one per heading.
            groups: list[list[str]] = [[]]
            size = 0
            for _, sub_text in self._split_by_headers(body.strip(), unit_title):
                if groups[-1] and size + len(sub_text) > self.max_chars:
                    groups.append([])
                    size = 0
                groups[-1].append(sub_text)
                size += len(sub_text) + 2
            for number, group in enumerate(groups, start=1):
                title = unit_title if number == 1 else f"{unit_title} (part {number})"
                sections.append((title, f"{heading}\n\n" + "\n\n".join(group), heading))
        return sections

    @staticmethod
    def _unit_level(text: str) -> int | None:
        counts = {1: 0, 2: 0, 3: 0}
        for match in re.finditer(r"^(#{1,3})\s+\S", text, re.MULTILINE):
            counts[len(match.group(1))] += 1
        return next((lvl for lvl in (1, 2, 3) if counts[lvl] >= 2), None)

    def _split_by_headers(
        self, text: str, default_title: str, max_level: int = 4
    ) -> list[tuple[str, str]]:
        header_pattern = re.compile(rf"^(#{{1,{max_level}}})\s+(.+)$", re.MULTILINE)
        matches = list(header_pattern.finditer(text))

        if not matches:
            return [(default_title, text)]

        sections: list[tuple[str, str]] = []

        # Content before the first header
        first_start = matches[0].start()
        if first_start > 0:
            preamble = text[:first_start].strip()
            if preamble:
                sections.append((default_title, preamble))

        for i, match in enumerate(matches):
            header_title = match.group(2).strip()
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section_content = text[start:end].strip()
            sections.append((header_title, section_content))

        return sections

    def _split_large_section(self, text: str) -> list[str]:
        """Split a large section by paragraphs and sentences with overlap."""
        paragraphs = text.split("\n\n")
        chunks: list[str] = []
        current_chunk: list[str] = []
        current_length = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_len = len(para)
            if current_length + para_len + 2 <= self.max_chars:
                current_chunk.append(para)
                current_length += para_len + 2
            else:
                if current_chunk:
                    full_chunk = "\n\n".join(current_chunk)
                    chunks.append(full_chunk)

                    # Build overlap from end of current chunk
                    overlap_buffer: list[str] = []
                    overlap_len = 0
                    for p in reversed(current_chunk):
                        if overlap_len + len(p) <= self.overlap_chars:
                            overlap_buffer.insert(0, p)
                            overlap_len += len(p) + 2
                        else:
                            break

                    current_chunk = overlap_buffer
                    current_length = sum(len(p) + 2 for p in current_chunk)

                # If a single paragraph is longer than max_chars, split by sentences
                if para_len > self.max_chars:
                    sentence_chunks = self._split_by_sentences(para)
                    for sc in sentence_chunks:
                        chunks.append(sc)
                else:
                    current_chunk.append(para)
                    current_length += para_len + 2

        if current_chunk:
            full_chunk = "\n\n".join(current_chunk)
            chunks.append(full_chunk)

        return chunks

    def _split_by_sentences(self, text: str) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: list[str] = []
        current = ""

        for sent in sentences:
            if len(current) + len(sent) + 1 <= self.max_chars:
                current = f"{current} {sent}".strip()
            else:
                if current:
                    chunks.append(current)
                current = sent

        if current:
            chunks.append(current)
        return chunks
