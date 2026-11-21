"""Copy legacy local document objects to S3 before applying migration 0002.

Run from backend/ with production database and S3 environment variables set.
The command is intentionally read-only against the database; Alembic 0002
assigns the same basename keys after the bytes have been verified in S3.
"""
import hashlib
from pathlib import Path, PurePosixPath, PureWindowsPath
import sys

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.db.database import engine
from app.services.storage import S3StorageBackend


def main() -> None:
    if settings.STORAGE_BACKEND != "s3":
        raise RuntimeError("Set STORAGE_BACKEND=s3 before running this migration utility")
    local_root = Path(settings.UPLOAD_DIR).resolve()
    s3 = S3StorageBackend()
    copied: dict[str, str] = {}

    inspector = inspect(engine)
    if "documents" not in inspector.get_table_names():
        print("No legacy document table found; Alembic will create the new schema.")
        return
    columns = {column["name"] for column in inspector.get_columns("documents")}
    if "file_path" not in columns:
        print("Legacy document paths were already migrated.")
        return

    with engine.connect() as connection:
        documents = connection.execute(text(
            "SELECT id, file_path, filename, file_hash FROM documents"
        )).mappings().all()

    for document in documents:
        old_path = document["file_path"] or ""
        basename = PureWindowsPath(old_path).name or PurePosixPath(old_path).name
        if not basename or basename in {".", ".."}:
            basename = Path(document["filename"] or document["id"]).name
        key = basename
        if key in copied and copied[key] != document["file_hash"]:
            raise RuntimeError(f"Legacy object key collision for {key!r}; resolve it before migration")

        legacy_path = Path(old_path)
        candidates = [legacy_path] if legacy_path.is_absolute() else [local_root / legacy_path, local_root / basename]
        source = next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)
        if source is None or (local_root not in source.parents and source != local_root):
            raise FileNotFoundError(f"Legacy document {document['id']} is unavailable under UPLOAD_DIR")

        payload = source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != document["file_hash"]:
            raise RuntimeError(f"SHA-256 mismatch for legacy document {document['id']}")
        content_type = "application/pdf" if basename.lower().endswith(".pdf") else "application/octet-stream"
        s3.upload_file(payload, key, content_type)
        if hashlib.sha256(s3.download_bytes(key)).hexdigest() != digest:
            raise RuntimeError(f"S3 integrity check failed for legacy document {document['id']}")
        copied[key] = digest
        print(f"Verified {document['id']} -> {key}")

    print(f"Verified {len(documents)} legacy document(s). Apply Alembic migration 0002 next.")


if __name__ == "__main__":
    main()
