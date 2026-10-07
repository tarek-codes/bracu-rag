"""Ingest markdown documents from output/pages into a Chroma Cloud collection."""

import os
import sys
import time
import uuid
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from app.services.ingestion.chunker import MarkdownChunker

PAGES_DIR = Path(os.getenv("KB_PAGES_DIR", "output/pages"))
API_KEY = os.getenv("CHROMA_API_KEY", "")
DATABASE_NAME = os.getenv("CHROMA_DATABASE", "rag")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "rag")

DOCUMENTS = [
    {"filename": "about_bracu.md", "title": "About BRAC University"},
    {"filename": "admissions_and_rs_faqs.md", "title": "Admissions & Residential Semester FAQs"},
    {"filename": "course_drop_replace_form.md", "title": "Course Drop & Replace Form"},
    {"filename": "cse_advising_guidelines.md", "title": "CSE Academic Advising Guidelines"},
    {"filename": "cse_contributors.md", "title": "CSE Portal Contributors"},
    {"filename": "cse_course_prerequisites.md", "title": "CSE Course Prerequisites Directory"},
    {"filename": "cse_courses.md", "title": "CSE Course Catalog & Descriptions"},
    {"filename": "cse_faculty_directory.md", "title": "CSE Faculty & Staff Directory"},
    {"filename": "cse_faculty_profiles.md", "title": "CSE Faculty Profiles"},
    {"filename": "cse_obe_curriculum.md", "title": "CSE Outcome-Based Education (OBE) Curriculum"},
    {"filename": "cse_postgraduate_programs.md", "title": "CSE Postgraduate Degree Programs"},
    {"filename": "cse_student_forms.md", "title": "CSE Student Forms Directory"},
    {"filename": "cse_thesis_policy.md", "title": "CSE Undergraduate Thesis Policy & Rubric"},
    {"filename": "cse_thesis_supervisors.md", "title": "CSE Thesis & Project Supervisors Directory"},
    {"filename": "cse_thesis_synopses.md", "title": "CSE Thesis Synopses & Research Areas"},
    {"filename": "cse_undergraduate_programs.md", "title": "CSE Undergraduate Degree Programs"},
    {"filename": "inter_department_transfer_form.md", "title": "Inter-Department Transfer Form"},
    {"filename": "tuition_and_fees.md", "title": "Tuition & Fee Structure"},
]


def main() -> None:
    if not API_KEY:
        print("Missing CHROMA_API_KEY environment variable.")
        sys.exit(1)

    print("=" * 70)
    print("CHROMA CLOUD INGESTION PIPELINE")
    print("=" * 70)
    print(f"Target Database:   {DATABASE_NAME}")
    print(f"Target Collection: {COLLECTION_NAME}")
    print(f"Source Directory:  {PAGES_DIR}")
    print(f"Total Documents:   {len(DOCUMENTS)}")
    print("=" * 70)

    print("\n[1/4] Connecting to Chroma Cloud...")
    client = chromadb.CloudClient(
        api_key=API_KEY,
        database=DATABASE_NAME,
    )

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "BRAC University RAG Knowledge Base Chunks & Embeddings"},
    )
    initial_count = collection.count()
    print(f"Connected successfully! Current chunks in collection '{COLLECTION_NAME}': {initial_count}")

    if initial_count > 0:
        print("Clearing old collection items for a fresh, clean ingestion...")
        client.delete_collection(COLLECTION_NAME)
        collection = client.create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "BRAC University RAG Knowledge Base Chunks & Embeddings"},
        )
        print(f"Collection reset. Current count: {collection.count()}")

    print("\n[2/4] Chunking markdown documents...")
    chunker = MarkdownChunker(min_chars=200, max_chars=2800, overlap_chars=300)
    all_chunks = []

    for doc_info in DOCUMENTS:
        fpath = PAGES_DIR / doc_info["filename"]
        if not fpath.is_file():
            print(f"WARNING: File not found: {fpath}")
            continue
        text = fpath.read_text(encoding="utf-8")
        chunks = chunker.chunk_document(text, doc_info["title"])
        doc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, doc_info["filename"]))

        for c in chunks:
            chunk_unique_id = f"{doc_info['filename']}#chunk-{c.chunk_index}"
            all_chunks.append(
                {
                    "id": chunk_unique_id,
                    "document_id": doc_id,
                    "document_title": doc_info["title"],
                    "chunk_title": c.title or doc_info["title"],
                    "source_path": f"pages/{doc_info['filename']}",
                    "chunk_index": c.chunk_index,
                    "content": c.content,
                }
            )
        print(f"  - {doc_info['title']:<45} ({len(chunks):>4} chunks)")

    total_chunks = len(all_chunks)
    print(f"\nTotal chunks prepared: {total_chunks}")

    print("\n[3/4] Loading embedding model 'sentence-transformers/all-MiniLM-L6-v2'...")
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    model.max_seq_length = 512

    contents = [c["content"] for c in all_chunks]
    print(f"Generating embeddings for {len(contents)} chunks in batches of 64...")
    t0 = time.time()
    embeddings = model.encode(
        contents,
        batch_size=64,
        show_progress_bar=True,
        normalize_embeddings=True,
    ).tolist()
    embed_time = time.time() - t0
    print(f"Embeddings generated in {embed_time:.2f}s ({len(embeddings)} vectors, dim={len(embeddings[0])})")

    print(f"\n[4/4] Uploading {total_chunks} items to Chroma Cloud collection '{COLLECTION_NAME}'...")
    upload_batch_size = 100
    total_uploaded = 0
    t_upload_start = time.time()

    for i in range(0, total_chunks, upload_batch_size):
        batch_slice = slice(i, min(i + upload_batch_size, total_chunks))
        batch_items = all_chunks[batch_slice]
        batch_embeddings = embeddings[batch_slice]

        ids = [item["id"] for item in batch_items]
        docs = [item["content"] for item in batch_items]
        metadatas = [
            {
                "document_id": item["document_id"],
                "document_title": item["document_title"],
                "chunk_title": item["chunk_title"],
                "source_path": item["source_path"],
                "chunk_index": item["chunk_index"],
                "char_count": len(item["content"]),
            }
            for item in batch_items
        ]

        collection.add(
            ids=ids,
            embeddings=batch_embeddings,
            documents=docs,
            metadatas=metadatas,
        )
        total_uploaded += len(ids)
        print(f"  Uploaded batch [{total_uploaded}/{total_chunks}] ({total_uploaded * 100 // total_chunks}%)")

    upload_time = time.time() - t_upload_start
    final_count = collection.count()

    print("\n" + "=" * 70)
    print("CHROMA CLOUD INGESTION COMPLETE & VERIFIED")
    print("=" * 70)
    print(f"Database:           {DATABASE_NAME}")
    print(f"Collection:         {COLLECTION_NAME}")
    print(f"Total Chunks:       {final_count}")
    print(f"Embedding Time:     {embed_time:.2f}s")
    print(f"Upload Time:        {upload_time:.2f}s")
    print("=" * 70)


if __name__ == "__main__":
    main()
