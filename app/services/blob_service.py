import io
import logging

from azure.storage.blob import BlobServiceClient, ContainerClient
from azure.core.exceptions import AzureError
from fastapi import UploadFile

from app.config import settings

logger = logging.getLogger(__name__)


def _get_container_client() -> ContainerClient:
    blob_service = BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)
    container = blob_service.get_container_client(settings.azure_container_name)
    if not container.exists():
        container.create_container()
    return container


def upload_blob(blob_name: str, file: UploadFile) -> str:
    """Upload a file to Azure Blob Storage. Returns the blob URL."""
    container = _get_container_client()
    blob_client = container.get_blob_client(blob_name)
    blob_client.upload_blob(file.file, overwrite=True, max_concurrency=4)
    logger.info(f"Uploaded blob: {blob_name}")
    return blob_client.url


def download_blob_as_stream(blob_name: str) -> io.TextIOWrapper:
    """Download a blob as a text stream. Does NOT load entire file in memory.

    Returns a line-iterable text stream suitable for csv.reader/DictReader.
    """
    container = _get_container_client()
    blob_client = container.get_blob_client(blob_name)
    stream = blob_client.download_blob()
    byte_stream = io.BytesIO()
    stream.readinto(byte_stream)
    byte_stream.seek(0)
    return io.TextIOWrapper(byte_stream, encoding="utf-8")
