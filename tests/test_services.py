"""Tests for job_service, queue_service, and blob_service logic."""

import uuid
from unittest.mock import MagicMock, patch, call

from app.db.models import Job
from app.services import job_service


class TestJobServiceCreateJob:
    def test_create_job_sets_pending_status(self):
        mock_db = MagicMock()
        mock_db.refresh = MagicMock(side_effect=lambda j: None)

        job = job_service.create_job(mock_db, filename="test.csv", blob_url="http://blob/test.csv")

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        added_job = mock_db.add.call_args[0][0]
        assert added_job.status == "PENDING"
        assert added_job.filename == "test.csv"
        assert added_job.blob_url == "http://blob/test.csv"

    def test_create_job_generates_uuid(self):
        mock_db = MagicMock()
        mock_db.refresh = MagicMock(side_effect=lambda j: None)

        job_service.create_job(mock_db, filename="test.csv", blob_url="http://blob/test.csv")

        added_job = mock_db.add.call_args[0][0]
        assert added_job.id is not None
        assert isinstance(added_job.id, uuid.UUID)


class TestJobServiceGetJob:
    def test_get_existing_job(self):
        mock_db = MagicMock()
        expected_job = Job()
        expected_job.id = uuid.uuid4()
        mock_db.query.return_value.filter.return_value.first.return_value = expected_job

        result = job_service.get_job(mock_db, str(expected_job.id))

        assert result == expected_job
        mock_db.query.assert_called_once_with(Job)

    def test_get_nonexistent_job_returns_none(self):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = job_service.get_job(mock_db, str(uuid.uuid4()))

        assert result is None


class TestJobServiceUpdateStatus:
    def test_update_to_processing(self):
        mock_db = MagicMock()
        job_id = str(uuid.uuid4())

        job_service.update_job_status(mock_db, job_id, "PROCESSING")

        mock_db.query.return_value.filter.return_value.update.assert_called_once_with(
            {"status": "PROCESSING"}
        )
        mock_db.commit.assert_called_once()

    def test_update_to_completed_with_records(self):
        mock_db = MagicMock()
        job_id = str(uuid.uuid4())

        job_service.update_job_status(mock_db, job_id, "COMPLETED", records_processed=500)

        mock_db.query.return_value.filter.return_value.update.assert_called_once_with(
            {"status": "COMPLETED", "records_processed": 500}
        )

    def test_update_to_failed_with_error(self):
        mock_db = MagicMock()
        job_id = str(uuid.uuid4())

        job_service.update_job_status(mock_db, job_id, "FAILED", error_message="Parse error")

        mock_db.query.return_value.filter.return_value.update.assert_called_once_with(
            {"status": "FAILED", "error_message": "Parse error"}
        )

    def test_update_without_optional_fields(self):
        mock_db = MagicMock()
        job_id = str(uuid.uuid4())

        job_service.update_job_status(mock_db, job_id, "PENDING")

        update_dict = mock_db.query.return_value.filter.return_value.update.call_args[0][0]
        assert "error_message" not in update_dict
        assert "records_processed" not in update_dict
