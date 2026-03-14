"""Queue consumer worker - listens for CSV processing jobs."""

import json
import logging
import time

from app.db.database import SessionLocal
from app.services import blob_service, queue_service, job_service
from app.worker.processor import process_csv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

POLL_INTERVAL = 5  # seconds between queue polls


def main():
    logger.info("Worker started. Polling queue for messages...")

    while True:
        try:
            messages = list(queue_service.receive_messages(max_messages=1, visibility_timeout=600))

            if not messages:
                time.sleep(POLL_INTERVAL)
                continue

            for message in messages:
                handle_message(message)

        except KeyboardInterrupt:
            logger.info("Worker shutting down.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in poll loop: {e}")
            time.sleep(POLL_INTERVAL)


def handle_message(message):
    """Process a single queue message."""
    payload = json.loads(message.content)
    job_id = payload["job_id"]
    blob_name = payload["blob_name"]

    logger.info(f"Processing job {job_id} - blob: {blob_name}")

    db = SessionLocal()
    try:
        # Mark as PROCESSING
        job_service.update_job_status(db, job_id, "PROCESSING")

        # Download CSV from Blob Storage as stream (memory-efficient)
        csv_stream = blob_service.download_blob_as_stream(blob_name)

        # Process CSV stream and bulk insert into PostgreSQL
        records = process_csv(csv_stream)

        # Mark as COMPLETED
        job_service.update_job_status(db, job_id, "COMPLETED", records_processed=records)
        logger.info(f"Job {job_id} completed. {records} records inserted.")

        # Delete message from queue
        queue_service.delete_message(message)

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        job_service.update_job_status(db, job_id, "FAILED", error_message=str(e))
        # Delete message to avoid infinite retry loop
        try:
            queue_service.delete_message(message)
        except Exception:
            pass
    finally:
        db.close()


if __name__ == "__main__":
    main()
