"""Pluggable storage for uploaded bid documents."""
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import quote
import os

from fastapi import HTTPException

from app.core.config import settings


def validate_upload(filename: str, content_type: str | None, file_bytes: bytes) -> tuple[str, str]:
    """Validate extension, declared MIME, size, and file signature."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File extension '{ext}' is not allowed.")
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded document is empty.")
    if len(file_bytes) > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail=f"File size exceeds limit ({settings.MAX_FILE_SIZE_BYTES / (1024*1024):.1f}MB)")
    mime_types = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
    expected = mime_types[ext]
    if not content_type or content_type.lower() != expected:
        raise HTTPException(status_code=400, detail="Declared MIME type does not match the file extension.")
    signatures = {".pdf": b"%PDF-", ".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}
    if not file_bytes.startswith(signatures[ext]):
        raise HTTPException(status_code=400, detail=f"File content does not match declared extension '{ext}'. Upload rejected.")
    return ext, expected


class StorageBackend(ABC):
    @abstractmethod
    def upload_file(self, file_bytes: bytes, key: str, content_type: str) -> None: ...

    @abstractmethod
    def get_download_url(self, key: str, expires_in: int = 3600) -> str: ...

    @abstractmethod
    def download_bytes(self, key: str) -> bytes: ...

    @abstractmethod
    def delete_file(self, key: str) -> None: ...

    @abstractmethod
    def file_exists(self, key: str) -> bool: ...


class LocalStorageBackend(StorageBackend):
    def __init__(self, upload_dir: str | Path | None = None):
        self.upload_dir = Path(upload_dir or settings.UPLOAD_DIR).resolve()
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        supplied = Path(key)
        path = supplied.resolve() if supplied.is_absolute() else (self.upload_dir / supplied).resolve()
        if self.upload_dir not in path.parents:
            raise ValueError("Invalid storage key")
        return path

    def upload_file(self, file_bytes: bytes, key: str, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(file_bytes)

    def get_download_url(self, key: str, expires_in: int = 3600) -> str:
        # Local documents are served through the authenticated API view route.
        return f"/api/bids/documents/storage?key={quote(key, safe='')}"

    def download_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete_file(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def file_exists(self, key: str) -> bool:
        return self._path(key).is_file()


class S3StorageBackend(StorageBackend):
    def __init__(self, *, endpoint_url=None, bucket_name=None, access_key_id=None, secret_access_key=None, region=None):
        import boto3
        self.bucket_name = bucket_name or settings.S3_BUCKET_NAME
        self.client = boto3.client(
            "s3", endpoint_url=endpoint_url or settings.S3_ENDPOINT_URL,
            aws_access_key_id=access_key_id or settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=secret_access_key or settings.S3_SECRET_ACCESS_KEY,
            region_name=region or settings.S3_REGION,
        )

    def upload_file(self, file_bytes: bytes, key: str, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket_name, Key=key, Body=file_bytes, ContentType=content_type)

    def get_download_url(self, key: str, expires_in: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket_name, "Key": key}, ExpiresIn=expires_in
        )

    def download_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket_name, Key=key)["Body"].read()

    def delete_file(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket_name, Key=key)

    def file_exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return False
            raise


def get_storage_backend() -> StorageBackend:
    if settings.STORAGE_BACKEND == "s3":
        return S3StorageBackend()
    return LocalStorageBackend()
