"""Ingest all 18 clean markdown documents from output/pages into PostgreSQL vector DB.
"""

import asyncio
from pathlib import Path
import time
from sqlalchemy import text

from app.db.session import async_session_factory
from app.models.document import IngestionJob
from app.services.ingestion.pipeline import IngestionPipeline, IngestionStats

ALL_DOCUMENTS = [
    {
        "filename": "about_bracu.md",
        "rel_path": "pages/about_bracu.md",
        "title": "About BRAC University",
    },
    {
        "filename": "admissions_and_rs_faqs.md",
        "rel_path": "pages/admissions_and_rs_faqs.md",
        "title": "Admissions & Residential Semester FAQs",
    },
    {
        "filename": "course_drop_replace_form.md",
        "rel_path": "pages/course_drop_replace_form.md",
        "title": "Course Drop & Replace Form",
    },
    {
        "filename": "cse_advising_guidelines.md",
        "rel_path": "pages/cse_advising_guidelines.md",
        "title": "CSE Academic Advising Guidelines",
    },
    {
        "filename": "cse_contributors.md",
        "rel_path": "pages/cse_contributors.md",
        "title": "CSE Portal Contributors",
    },
    {
        "filename": "cse_course_prerequisites.md",
        "rel_path": "pages/cse_course_prerequisites.md",
        "title": "CSE Course Prerequisites Directory",
    },
    {
        "filename": "cse_courses.md",
        "rel_path": "pages/cse_courses.md",
        "title": "CSE Course Catalog & Descriptions",
    },
    {
        "filename": "cse_faculty_directory.md",
        "rel_path": "pages/cse_faculty_directory.md",
        "title": "CSE Faculty & Staff Directory",
    },
    {
        "filename": "cse_faculty_profiles.md",
        "rel_path": "pages/cse_faculty_profiles.md",
        "title": "CSE Faculty Profiles",
    },
    {
        "filename": "cse_obe_curriculum.md",
        "rel_path": "pages/cse_obe_curriculum.md",
        "title": "CSE Outcome-Based Education (OBE) Curriculum",
    },
    {
        "filename": "cse_postgraduate_programs.md",
        "rel_path": "pages/cse_postgraduate_programs.md",
        "title": "CSE Postgraduate Degree Programs",
    },
    {
        "filename": "cse_student_forms.md",
        "rel_path": "pages/cse_student_forms.md",
        "title": "CSE Student Forms Directory",
    },
    {
        "filename": "cse_thesis_policy.md",
        "rel_path": "pages/cse_thesis_policy.md",
        "title": "CSE Undergraduate Thesis Policy & Rubric",
    },
    {
        "filename": "cse_thesis_supervisors.md",
        "rel_path": "pages/cse_thesis_supervisors.md",
        "title": "CSE Thesis & Project Supervisors Directory",
    },
    {
        "filename": "cse_thesis_synopses.md",
        "rel_path": "pages/cse_thesis_synopses.md",
        "title": "CSE Thesis Synopses & Research Areas",
    },
    {
        "filename": "cse_undergraduate_programs.md",
        "rel_path": "pages/cse_undergraduate_programs.md",
        "title": "CSE Undergraduate Degree Programs",
    },
    {
        "filename": "inter_department_transfer_form.md",
        "rel_path": "pages/inter_department_transfer_form.md",
        "title": "Inter-Department Transfer Form",
    },
    {
        "filename": "tuition_and_fees.md",
        "rel_path": "pages/tuition_and_fees.md",
        "title": "Tuition & Fee Structure",
    },
]

async def main():
    start_total = time.time()
    base_dir = Path(r"c:\Users\tarek\Desktop\brac-rag\output\pages")
    print(f"Starting ingestion of {len(ALL_DOCUMENTS)} clean official documents...")
    print(f"Source directory: {base_dir}\n")

    async with async_session_factory() as db:
        # Clean existing pages document records so all chunks are freshly embedded
        await db.execute(text("DELETE FROM documents WHERE source_path LIKE 'pages/%'"))
        await db.commit()

        job = IngestionJob(source_type="bulk", status="processing")
        db.add(job)
        await db.commit()
        await db.refresh(job)

        pipeline = IngestionPipeline(db)
        overall_stats = IngestionStats()

        for idx, doc_info in enumerate(ALL_DOCUMENTS, start=1):
            file_path = base_dir / doc_info["filename"]
            if not file_path.is_file():
                print(f"[{idx}/{len(ALL_DOCUMENTS)}] ERROR: File not found: {file_path}")
                continue

            content_bytes = file_path.read_bytes()
            print(f"[{idx}/{len(ALL_DOCUMENTS)}] Ingesting '{doc_info['title']}' ({file_path.name}, {len(content_bytes)} bytes)...")
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

            chunks_count = 0
            if doc:
                res = await db.execute(
                    text("SELECT count(*) FROM document_chunks WHERE document_id = :did AND embedding IS NOT NULL"),
                    {"did": doc.id},
                )
                chunks_count = res.scalar() or 0

            print(f"       -> Done in {elapsed:.2f}s | Embedded chunks: {chunks_count} | Added: {doc_stats.chunks_added}\n")

            overall_stats.files_added += doc_stats.files_added
            overall_stats.files_updated += doc_stats.files_updated
            overall_stats.files_skipped += doc_stats.files_skipped
            overall_stats.chunks_added += doc_stats.chunks_added

        job.status = "done"
        job.stats = overall_stats.to_dict()
        await db.commit()

        # Verification summary
        print("=" * 70)
        print("VERIFICATION OF INGESTED CLEAN DOCUMENTS IN DATABASE:")
        print("=" * 70)
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
            print(f"- {r.title:<46} | Path: {r.source_path:<36} | Chunks: {r.total_chunks:>4} | Embedded: {r.embedded_chunks:>4}")
            total_chunks += r.total_chunks
            total_embedded += r.embedded_chunks

        total_time = time.time() - start_total
        print("=" * 70)
        print(f"Total Documents: {len(rows)}")
        print(f"Total Chunks:    {total_chunks}")
        print(f"Total Embedded:  {total_embedded}")
        print(f"Completed in:    {total_time:.2f}s")
        print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
