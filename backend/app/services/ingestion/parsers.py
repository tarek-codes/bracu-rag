import os
import re
from io import BytesIO
from typing import Any

import httpx
import structlog

from app.services.ingestion.ssrf import validate_url_for_ssrf

logger = structlog.get_logger("ingestion.parsers")


class ParsedContent:
    def __init__(
        self,
        title: str,
        text: str,
        mime_type: str,
        meta_info: dict[str, Any] | None = None,
        page_chunks: list[dict[str, Any]] | None = None,
    ):
        self.title = title
        self.text = text
        self.mime_type = mime_type
        self.meta_info = meta_info or {}
        self.page_chunks = page_chunks or []


def normalize_text(text: str) -> str:
    """Normalize text whitespace and newlines for deterministic hashing."""
    # Convert CRLF to LF
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Replace non-breaking spaces
    text = text.replace("\xa0", " ")
    # Strip trailing whitespace on lines
    lines = [re.sub(r"[ \t]+$", "", line) for line in text.split("\n")]
    # Remove consecutive empty lines beyond 2
    cleaned_lines = []
    empty_count = 0
    for line in lines:
        if not line.strip():
            empty_count += 1
            if empty_count <= 1:
                cleaned_lines.append("")
        else:
            empty_count = 0
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def parse_text_or_markdown(content_bytes: bytes, filename: str) -> ParsedContent:
    """Parse UTF-8 plain text or Markdown files."""
    try:
        raw_text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raw_text = content_bytes.decode("latin-1", errors="replace")

    normalized = normalize_text(raw_text)

    title = os.path.splitext(os.path.basename(filename))[0]

    # Check for YAML frontmatter title
    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", normalized, re.DOTALL)
    if frontmatter_match:
        for fline in frontmatter_match.group(1).splitlines():
            if fline.strip().startswith("title:"):
                raw_val = fline.split("title:", 1)[1].strip().strip("\"'")
                if raw_val and not raw_val.lower().startswith("sites_default_files"):
                    title = raw_val
                    break

    # If title is filename or empty, extract first meaningful heading (excluding 'Page X')
    if not title or title == os.path.splitext(os.path.basename(filename))[0]:
        for line in normalized.split("\n"):
            line_clean = line.strip()
            if line_clean.startswith("#"):
                candidate = re.sub(r"^#+\s*", "", line_clean).strip()
                if candidate and not re.match(r"^page\s*\d+$", candidate, re.IGNORECASE):
                    title = candidate
                    break

    mime_type = "text/markdown" if filename.endswith((".md", ".markdown")) else "text/plain"
    return ParsedContent(
        title=title,
        text=normalized,
        mime_type=mime_type,
        meta_info={"format": "markdown" if "markdown" in mime_type else "text"},
    )


def parse_pdf(content_bytes: bytes, filename: str) -> ParsedContent:
    """Parse PDF document using pymupdf4llm preserving tables and headers."""
    import fitz  # PyMuPDF
    import pymupdf4llm

    doc = fitz.open(stream=content_bytes, filetype="pdf")
    page_count = len(doc)

    title = os.path.splitext(os.path.basename(filename))[0]
    # Check document metadata for title
    doc_meta = doc.metadata or {}
    if doc_meta.get("title") and doc_meta["title"].strip():
        title = doc_meta["title"].strip()

    # Extract markdown with pymupdf4llm
    md_text = pymupdf4llm.to_markdown(doc)
    doc.close()

    normalized = normalize_text(md_text)
    return ParsedContent(
        title=title,
        text=normalized,
        mime_type="application/pdf",
        meta_info={"page_count": page_count, "format": "pdf"},
    )


def parse_docx(content_bytes: bytes, filename: str) -> ParsedContent:
    """Parse Microsoft Word DOCX files."""
    import docx

    file_stream = BytesIO(content_bytes)
    doc = docx.Document(file_stream)

    paragraphs = []
    title = os.path.splitext(os.path.basename(filename))[0]
    first_heading_found = False

    for para in doc.paragraphs:
        p_text = para.text.strip()
        if not p_text:
            continue

        style_name = para.style.name if para.style else ""
        if style_name.startswith("Heading"):
            level = 1
            if len(style_name) > 7 and style_name[7:].isdigit():
                level = int(style_name[7:])
            paragraphs.append(f"{'#' * level} {p_text}")
            if not first_heading_found:
                title = p_text
                first_heading_found = True
        else:
            paragraphs.append(p_text)

    # Also capture simple tables
    for table in doc.tables:
        table_rows = []
        for row in table.rows:
            row_text = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            table_rows.append("| " + " | ".join(row_text) + " |")
        if table_rows:
            paragraphs.append("\n" + "\n".join(table_rows) + "\n")

    full_text = "\n\n".join(paragraphs)
    normalized = normalize_text(full_text)

    return ParsedContent(
        title=title,
        text=normalized,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        meta_info={"format": "docx"},
    )


async def parse_url(url: str, timeout_seconds: float = 20.0) -> ParsedContent:
    """Fetch and parse web page using trafilatura with SSRF guard and Cloudflare bypass."""
    safe_url = validate_url_for_ssrf(url)
    import trafilatura

    html = ""
    # Try fetching with curl_cffi with realistic browser TLS fingerprinting (bypasses Cloudflare / anti-bot)
    try:
        from curl_cffi.requests import AsyncSession

        async with AsyncSession(impersonate="chrome124", timeout=timeout_seconds) as session:
            resp = await session.get(safe_url, headers={"Accept-Language": "en-US,en;q=0.9"})
            if resp.status_code == 200 and "Just a moment..." not in resp.text:
                html = resp.text
            elif resp.status_code != 200:
                resp.raise_for_status()
    except Exception as exc:
        logger.warning("curl_cffi_fetch_failed_falling_back_to_httpx", url=safe_url, error=str(exc))

    if not html:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout_seconds) as client:
            response = await client.get(
                safe_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            response.raise_for_status()
            html = response.text

    extracted = trafilatura.extract(
        html,
        include_links=True,
        include_tables=True,
        include_images=False,
        output_format="markdown",
    )
    if not extracted:
        extracted = ""

    extracted_meta = trafilatura.extract_metadata(html)
    title = url
    if extracted_meta and extracted_meta.title:
        title = extracted_meta.title.strip()

    normalized = normalize_text(extracted)
    return ParsedContent(
        title=title,
        text=normalized,
        mime_type="text/html",
        meta_info={"url": safe_url, "format": "html"},
    )
