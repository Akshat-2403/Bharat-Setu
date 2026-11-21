"""Replace persisted filesystem paths with storage keys.

Revision ID: 0002_document_storage_keys
Revises: 0001_initial_schema
"""
from alembic import op
import sqlalchemy as sa
from pathlib import PurePosixPath, PureWindowsPath

revision = "0002_document_storage_keys"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("documents")}
    if "storage_key" not in columns:
        op.add_column("documents", sa.Column("storage_key", sa.String(), nullable=True))
        columns.add("storage_key")
    connection = op.get_bind()
    if "file_path" in columns:
        rows = connection.execute(sa.text("SELECT id, file_path FROM documents WHERE storage_key IS NULL")).mappings()
        for row in rows:
            old_path = row["file_path"] or ""
            # Preserve the old object basename (including bid prefix) so local files
            # remain addressable after migration without persisting absolute paths.
            key = PureWindowsPath(old_path).name or PurePosixPath(old_path).name
            if not key or key in {".", ".."}:
                key = row["id"]
            connection.execute(
                sa.text("UPDATE documents SET storage_key = :key WHERE id = :id"),
                {"key": key, "id": row["id"]},
            )
        with op.batch_alter_table("documents") as batch_op:
            batch_op.alter_column("storage_key", existing_type=sa.String(), nullable=False)
            batch_op.drop_column("file_path")
    elif sa.inspect(connection).get_columns("documents"):
        with op.batch_alter_table("documents") as batch_op:
            batch_op.alter_column("storage_key", existing_type=sa.String(), nullable=False)


def downgrade():
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("documents")}
    if "storage_key" in columns:
        op.add_column("documents", sa.Column("file_path", sa.String(), nullable=True))
        connection.execute(sa.text("UPDATE documents SET file_path = storage_key"))
        with op.batch_alter_table("documents") as batch_op:
            batch_op.alter_column("file_path", existing_type=sa.String(), nullable=False)
            batch_op.drop_column("storage_key")
