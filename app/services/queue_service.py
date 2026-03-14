import json

from azure.storage.queue import QueueClient

from app.config import settings


def _get_queue_client() -> QueueClient:
    client = QueueClient.from_connection_string(
        settings.azure_storage_connection_string,
        queue_name=settings.azure_queue_name,
    )
    try:
        client.create_queue()
    except Exception:
        pass  # Queue already exists
    return client


def send_message(job_id: str, blob_name: str) -> None:
    """Send a processing message to the queue."""
    queue = _get_queue_client()
    message = json.dumps({"job_id": job_id, "blob_name": blob_name})
    queue.send_message(message)


def receive_messages(max_messages: int = 1, visibility_timeout: int = 300):
    """Receive messages from the queue. Returns list of messages."""
    queue = _get_queue_client()
    return queue.receive_messages(
        max_messages=max_messages,
        visibility_timeout=visibility_timeout,
    )


def delete_message(message) -> None:
    """Delete a message after successful processing."""
    queue = _get_queue_client()
    queue.delete_message(message)
