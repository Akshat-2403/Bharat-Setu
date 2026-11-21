import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.services.storage import LocalStorageBackend, S3StorageBackend, validate_upload


def test_local_storage_round_trip_and_download_route(tmp_path):
    storage = LocalStorageBackend(tmp_path)
    payload = b"%PDF-1.4\nexample"
    storage.upload_file(payload, "bids/123/document.pdf", "application/pdf")
    assert storage.download_bytes("bids/123/document.pdf") == payload
    assert storage.file_exists("bids/123/document.pdf")
    assert storage.get_download_url("bids/123/document.pdf").startswith("/api/bids/documents/storage?")
    storage.delete_file("bids/123/document.pdf")
    assert not storage.file_exists("bids/123/document.pdf")


def test_local_storage_rejects_path_traversal(tmp_path):
    storage = LocalStorageBackend(tmp_path)
    with pytest.raises(ValueError):
        storage.upload_file(b"x", "../outside.pdf", "application/pdf")


def test_s3_storage_uses_s3_compatible_client_operations():
    storage = S3StorageBackend.__new__(S3StorageBackend)
    storage.bucket_name = "documents"

    class Body:
        def read(self):
            return b"payload"

    class Client:
        def put_object(self, **kwargs):
            self.upload = kwargs

        def get_object(self, **kwargs):
            return {"Body": Body()}

        def delete_object(self, **kwargs):
            self.deleted = kwargs

        def generate_presigned_url(self, operation, Params, ExpiresIn):
            return f"https://objects.test/{Params['Key']}?expires={ExpiresIn}"

    storage.client = Client()
    storage.upload_file(b"payload", "bids/1/doc.pdf", "application/pdf")
    assert storage.client.upload["Bucket"] == "documents"
    assert storage.client.upload["ContentType"] == "application/pdf"
    assert storage.download_bytes("bids/1/doc.pdf") == b"payload"
    assert storage.get_download_url("bids/1/doc.pdf", 120).endswith("expires=120")
    storage.delete_file("bids/1/doc.pdf")
    assert storage.client.deleted["Key"] == "bids/1/doc.pdf"


@pytest.mark.parametrize(
    ("filename", "content_type", "payload"),
    [
        ("document.exe", "application/pdf", b"%PDF-1.4"),
        ("document.pdf", "image/png", b"%PDF-1.4"),
        ("document.pdf", "application/pdf", b"not a pdf"),
        ("document.pdf", "application/pdf", b""),
    ],
)
def test_upload_validation_rejects_invalid_files(filename, content_type, payload):
    with pytest.raises(HTTPException) as exc_info:
        validate_upload(filename, content_type, payload)
    assert exc_info.value.status_code == 400


def test_upload_validation_accepts_pdf():
    assert validate_upload("safe.pdf", "application/pdf", b"%PDF-1.4\nbody") == (".pdf", "application/pdf")


def test_production_requires_s3_storage():
    with pytest.raises(ValueError, match="STORAGE_BACKEND=s3"):
        Settings(ENVIRONMENT="production", STORAGE_BACKEND="local", LLM_PROVIDER="gemini", GEMINI_API_KEY="test-key")


def test_production_requires_all_s3_credentials(monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_SEED", "false")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")
    with pytest.raises(ValueError, match="S3 storage configuration"):
        Settings(
            ENVIRONMENT="production", STORAGE_BACKEND="s3",
            LLM_PROVIDER="gemini", GEMINI_API_KEY="test-key",
            DATABASE_URL="postgresql+psycopg://user:pass@localhost/db",
            JWT_SECRET_KEY="a" * 40,
        )
