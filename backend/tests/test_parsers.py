import pytest
from fastapi import HTTPException

from app.services.ingestion.parsers import (
    normalize_text,
    parse_text_or_markdown,
)
from app.services.ingestion.ssrf import validate_url_for_ssrf


def test_text_normalization() -> None:
    raw = "Line 1  \r\n\r\n\r\n\r\nLine 2 \xa0 with non-breaking space   "
    normalized = normalize_text(raw)
    assert "\r" not in normalized
    assert "\xa0" not in normalized
    assert "Line 1\n\nLine 2   with non-breaking space" in normalized


def test_parse_markdown_extracts_title_and_format() -> None:
    md_content = b"# BRACU CSE Department\n\nComputer Science curriculum details."
    parsed = parse_text_or_markdown(md_content, "cse_curriculum.md")
    assert parsed.title == "BRACU CSE Department"
    assert parsed.mime_type == "text/markdown"
    assert "Computer Science" in parsed.text


def test_ssrf_rejects_private_and_loopback_ips() -> None:
    blocked_urls = [
        "http://127.0.0.1/admin",
        "http://localhost:8000/secret",
        "http://192.168.1.1/router",
        "http://10.0.0.1/internal",
        "ftp://example.com/file",
        "file:///etc/passwd",
    ]
    for url in blocked_urls:
        with pytest.raises(HTTPException) as exc_info:
            validate_url_for_ssrf(url)
        assert exc_info.value.status_code == 400


def test_ssrf_allows_public_https_domain() -> None:
    # Safe public URL
    safe_url = "https://www.bracu.ac.bd/about"
    result = validate_url_for_ssrf(safe_url)
    assert result == safe_url
