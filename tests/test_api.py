"""Tests for FastAPI endpoints using mocked services."""

import io
import uuid
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.models import Job


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def sample_job():
    job = Job()
    job.id = uuid.uuid4()
    job.status = "PENDING"
    job.filename = "test.csv"
    job.blob_url = "http://azurite/test.csv"
    job.records_processed = 0
    job.created_at = datetime.now(timezone.utc)
    return job


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestUploadEndpoint:
    @patch("app.api.routes.queue_service")
    @patch("app.api.routes.job_service")
    @patch("app.api.routes.blob_service")
    def test_upload_csv_success(self, mock_blob, mock_job, mock_queue, client, sample_job):
        mock_blob.upload_blob.return_value = "http://azurite/blob/test.csv"
        mock_job.create_job.return_value = sample_job

        csv_content = b"date,product_id,quantity,price\n2026-01-01,1001,2,10.50\n"
        response = client.post(
            "/upload",
            files={"file": ("test.csv", io.BytesIO(csv_content), "text/csv")},
        )

        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["message"] == "File uploaded. Processing started."
        mock_blob.upload_blob.assert_called_once()
        mock_job.create_job.assert_called_once()
        mock_queue.send_message.assert_called_once()

    def test_upload_non_csv_rejected(self, client):
        response = client.post(
            "/upload",
            files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
        )
        assert response.status_code == 400
        assert "CSV" in response.json()["detail"]

    def test_upload_no_file_returns_422(self, client):
        response = client.post("/upload")
        assert response.status_code == 422


class TestJobStatusEndpoint:
    @patch("app.api.routes.job_service")
    def test_get_job_found(self, mock_job_service, client, sample_job):
        sample_job.status = "COMPLETED"
        mock_job_service.get_job.return_value = sample_job

        response = client.get(f"/job/{sample_job.id}")
        assert response.status_code == 200
        assert response.json()["status"] == "COMPLETED"

    @patch("app.api.routes.job_service")
    def test_get_job_not_found(self, mock_job_service, client):
        mock_job_service.get_job.return_value = None

        response = client.get(f"/job/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_get_job_invalid_uuid(self, client):
        response = client.get("/job/not-a-valid-uuid")
        assert response.status_code == 400
        assert "Invalid" in response.json()["detail"]

    @patch("app.api.routes.job_service")
    def test_get_job_pending(self, mock_job_service, client, sample_job):
        sample_job.status = "PENDING"
        mock_job_service.get_job.return_value = sample_job

        response = client.get(f"/job/{sample_job.id}")
        assert response.json()["status"] == "PENDING"

    @patch("app.api.routes.job_service")
    def test_get_job_failed(self, mock_job_service, client, sample_job):
        sample_job.status = "FAILED"
        mock_job_service.get_job.return_value = sample_job

        response = client.get(f"/job/{sample_job.id}")
        assert response.json()["status"] == "FAILED"


class TestCompletedJobsEndpoint:
    def test_completed_jobs_returns_list(self, client, sample_job):
        sample_job.status = "COMPLETED"
        sample_job.records_processed = 10

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_job]

        from app.db.database import get_db
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            response = client.get("/jobs/completed")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["status"] == "COMPLETED"
            assert data[0]["records_processed"] == 10
        finally:
            app.dependency_overrides.clear()
