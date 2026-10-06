import asyncio
import os
import sys
import time
from pathlib import Path

from app.db.session import async_session_factory
from app.models.document import IngestionJob, Document, DocumentChunk
from app.services.ingestion.pipeline import IngestionPipeline, IngestionStats
from sqlalchemy import text

DOCUMENTS_TO_INGEST = [
    {
        "filename": "Course_drop_replace_form.md",
        "rel_path": "pages/Course_drop_replace_form.md",
        "title": "Course Drop & Replace Form",
    },
    {
        "filename": "inter_department_transfer_form.md",
        "rel_path": "pages/inter_department_transfer_form.md",
        "title": "Inter-Department Transfer Form",
    },
    {
        "filename": "bracu_about_compiled.md",
        "rel_path": "pages/bracu_about_compiled.md",
        "title": "About BRAC University",
    },
    {
        "filename": "faqs_admissions_and_rs.md",
        "rel_path": "pages/faqs_admissions_and_rs.md",
        "title": "Admissions & Residential Semester FAQs",
    },
    {
        "filename": "tuition_and_other_fees.md",
        "rel_path": "pages/tuition_and_other_fees.md",
        "title": "Tuition & Fee Structure",
    },
    {
        "filename": "cse_bracu_ac_bd__courses_compiled.md",
        "rel_path": "pages/cse_bracu_ac_bd__courses_compiled.md",
        "title": "CSE Course Catalog",
    },
    {
        "filename": "cse_bracu_ac_bd__faculty_profiles_compiled.md",
        "rel_path": "pages/cse_bracu_ac_bd__faculty_profiles_compiled.md",
        "title": "CSE Faculty Profiles",
    },
    {
        "filename": "cse_bracu_ac_bd__postgraduate_program.md",
        "rel_path": "pages/cse_bracu_ac_bd__postgraduate_program.md",
        "title": "CSE Postgraduate Programs",
    },
    {
        "filename": "cse_bracu_ac_bd__undergraduate_program.md",
        "rel_path": "pages/cse_bracu_ac_bd__undergraduate_program.md",
        "title": "CSE Undergraduate Programs",
    },
    {
        "filename": "cse_bracu_ac_bd__student_forms.md",
        "rel_path": "pages/cse_bracu_ac_bd__student_forms.md",
        "title": "CSE Student Forms",
    },
    {
        "filename": "cse_bracu_ac_bd__thesis_synopses_compiled.md",
        "rel_path": "pages/cse_bracu_ac_bd__thesis_synopses_compiled.md",
        "title": "CSE Thesis Synopses",
    },
    {
        "filename": "thesis_policy_and_marking_rubric.md",
        "rel_path": "pages/thesis_policy_and_marking_rubric.md",
        "title": "CSE Thesis Policy & Rubric",
    },
]

async def main():
    start_total = time.time()
    base_dir = Path(r"c:\Users\tarek\Desktop\brac-rag\output\pages")
    print(f"Starting ingestion of {len(DOCUMENTS_TO_INGEST)} official documents...")
    print(f"Source directory: {base_dir}\n")

    async with async_session_factory() as db:
        # Clean existing pages document records so all 2635 chunks are freshly embedded
        await db.execute(text("DELETE FROM documents WHERE source_path LIKE 'pages/%'"))
        await db.commit()

        # Create an ingestion job record
        job = IngestionJob(source_type="bulk", status="processing")
        db.add(job)
        await db.commit()
        await db.refresh(job)

        pipeline = IngestionPipeline(db)
        overall_stats = IngestionStats()

        for idx, doc_info in enumerate(DOCUMENTS_TO_INGEST, start=1):
            file_path = base_dir / doc_info["filename"]
            if not file_path.is_file():
                print(f"[{idx}/{len(DOCUMENTS_TO_INGEST)}] ERROR: File not found: {file_path}")
                continue

            content_bytes = file_path.read_bytes()
            print(f"[{idx}/{len(DOCUMENTS_TO_INGEST)}] Ingesting '{doc_info['title']}' ({file_path.name}, {len(content_bytes)} bytes)...")
            t0 = time.time()

            doc_stats = IngestionStats()
            doc = await pipeline.ingest_file(
                file_path=doc_info["rel_path"],
                content_bytes=content_bytes,
                title=doc_info["title"],
                source_type="bulk",
                stats=doc_stats,
            )
            await db.commit()
            elapsed = time.time() - t0

            # Count chunks for this doc
            chunks_count = 0
            if doc:
                res = await db.execute(
                    text("SELECT count(*) FROM document_chunks WHERE document_id = :did AND embedding IS NOT NULL"),
                    {"did": doc.id},
                )
                chunks_count = res.scalar() or 0

            print(f"       -> Done in {elapsed:.2f}s | Embedded chunks: {chunks_count} | Added: {doc_stats.chunks_added}, Reused: {doc_stats.chunks_reused}\n")

            overall_stats.files_added += doc_stats.files_added
            overall_stats.files_updated += doc_stats.files_updated
            overall_stats.files_skipped += doc_stats.files_skipped
            overall_stats.chunks_added += doc_stats.chunks_added
            overall_stats.chunks_reused += doc_stats.chunks_reused

        job.status = "done"
        job.stats = overall_stats.to_dict()
        await db.commit()

        # Verification summary
        print("=" * 60)
        print("VERIFICATION OF INGESTED DOCUMENTS IN DATABASE:")
        print("=" * 60)
        res = await db.execute(text("""
            SELECT 
                d.id, 
                d.title, 
                d.source_path, 
                count(c.id) as total_chunks,
                count(c.embedding) as embedded_chunks
            FROM documents d
            LEFT JOIN document_chunks c ON c.document_id = d.id
            GROUP BY d.id, d.title, d.source_path
            ORDER BY d.title
        """))
        rows = list(res)
        total_chunks = 0
        total_embedded = 0
        for r in rows:
            print(f"- {r.title:<38} | Path: {r.source_path:<45} | Chunks: {r.total_chunks:>4} | Embedded: {r.embedded_chunks:>4}")
            total_chunks += r.total_chunks
            total_embedded += r.embedded_chunks

        total_time = time.time() - start_total
        print("=" * 60)
        print(f"Total Documents: {len(rows)}")
        print(f"Total Chunks:    {total_chunks}")
        print(f"Total Embedded:  {total_embedded}")
        print(f"Completed in:    {total_time:.2f}s")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
