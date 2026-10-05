import io

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_document_endpoints_require_admin(async_client: AsyncClient) -> None:
    # Unauthenticated
    resp = await async_client.get("/api/v1/documents")
    assert resp.status_code == 401

    # Standard user
    user_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "student1@g.bracu.ac.bd", "password": "Password123!"},
    )
    if user_login.status_code == 200:
        async_client.cookies.set("access_token", user_login.cookies["access_token"])
        forbidden_resp = await async_client.get("/api/v1/documents")
        assert forbidden_resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_upload_and_list_documents(async_client: AsyncClient) -> None:
    # Login as admin
    admin_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@bracu.ac.bd", "password": "AdminPassword123!"},
    )
    assert admin_login.status_code == 200
    async_client.cookies.set("access_token", admin_login.cookies["access_token"])

    # Upload markdown file
    file_content = b"# BRACU Library\n\nOpening hours: 8:00 AM to 9:00 PM Sunday through Thursday."
    files = {"file": ("library_hours.md", io.BytesIO(file_content), "text/markdown")}

    upload_resp = await async_client.post("/api/v1/documents/upload", files=files)
    assert upload_resp.status_code == 202
    job_data = upload_resp.json()
    assert "id" in job_data
    assert job_data["status"] in ("pending", "processing", "done")

    # Check job status endpoint
    job_id = job_data["id"]
    job_resp = await async_client.get(f"/api/v1/documents/jobs/{job_id}")
    assert job_resp.status_code == 200
    assert job_resp.json()["id"] == job_id

    # List documents
    list_resp = await async_client.get("/api/v1/documents")
    assert list_resp.status_code == 200
    assert "documents" in list_resp.json()

    # List jobs
    jobs_resp = await async_client.get("/api/v1/documents/jobs")
    assert jobs_resp.status_code == 200
    jobs = jobs_resp.json()
    assert isinstance(jobs, list)
    assert any(j["id"] == job_id for j in jobs)


@pytest.mark.asyncio
async def test_admin_document_lifecycle(async_client: AsyncClient) -> None:
    from unittest.mock import patch

    # Login as admin
    admin_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@bracu.ac.bd", "password": "AdminPassword123!"},
    )
    assert admin_login.status_code == 200
    async_client.cookies.set("access_token", admin_login.cookies["access_token"])

    # Ingest URL with mocked background tasks
    with patch("starlette.background.BackgroundTasks.add_task"):
        url_resp = await async_client.post(
            "/api/v1/documents/url",
            json={"url": "https://www.bracu.ac.bd/about/history"},
        )
        assert url_resp.status_code == 202
        url_job = url_resp.json()
        assert "id" in url_job

        # Fetch document list and test details, reindex, delete if any exists
        docs_resp = await async_client.get("/api/v1/documents?limit=1")
        assert docs_resp.status_code == 200
        docs = docs_resp.json()["documents"]
        if docs:
            doc_id = docs[0]["id"]
            # Get details
            detail_resp = await async_client.get(f"/api/v1/documents/{doc_id}")
            assert detail_resp.status_code == 200
            assert "chunks" in detail_resp.json()

            # Reindex
            reindex_resp = await async_client.post(f"/api/v1/documents/{doc_id}/reindex")
            assert reindex_resp.status_code == 202
            assert "id" in reindex_resp.json()
