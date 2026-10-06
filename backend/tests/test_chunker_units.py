from app.services.ingestion.chunker import MarkdownChunker

COURSES = """# Courses

## CSE110: Programming Language I

### Course Overview

Pre-requisite: N/A. Introduces programming with Java and basic problem solving techniques.

### Course Objectives

Develop problem solving skills and write programs using loops, arrays and methods well.

## CSE111: Programming Language II

### Course Overview

Pre-requisite: CSE110. Object oriented programming concepts, inheritance and polymorphism.

### List of Books

The Java Language Specification and other reference texts for the course material.
"""


def test_each_course_is_one_chunk_with_its_name() -> None:
    chunks = MarkdownChunker().chunk_document(COURSES, "Courses")
    assert len(chunks) == 2
    cse111 = next(c for c in chunks if "CSE111" in c.title)
    assert "Pre-requisite: CSE110" in cse111.content
    assert "List of Books" in cse111.content
    assert "CSE110: Programming Language I" not in cse111.content


def test_oversized_unit_splits_by_subheading_and_repeats_unit_heading() -> None:
    filler = "Detailed outcome text about the course. " * 40
    doc = f"## Big Course\n\n### Part A\n\n{filler}\n\n### Part B\n\n{filler}\n\n## Other Course\n\nShort body text that is long enough to be kept as its own chunk."
    chunks = MarkdownChunker(max_chars=1000).chunk_document(doc, "Doc")
    big = [c for c in chunks if "Big Course" in c.title]
    assert len(big) >= 2
    assert all(c.content.startswith("## Big Course") for c in big)


def test_chunking_is_deterministic() -> None:
    first = MarkdownChunker().chunk_document(COURSES, "Courses")
    second = MarkdownChunker().chunk_document(COURSES, "Courses")
    assert [c.chunk_hash for c in first] == [c.chunk_hash for c in second]
