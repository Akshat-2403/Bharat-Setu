"""Persist structured AI compliance assessments on bids.

Revision ID: 0003_bid_ai_assessment
Revises: 0002_document_storage_keys
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_bid_ai_assessment"
down_revision = "0002_document_storage_keys"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("bids")}
    if "ai_assessment" not in columns:
        op.add_column("bids", sa.Column("ai_assessment", sa.JSON(), nullable=True))


def downgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("bids")}
    if "ai_assessment" in columns:
        op.drop_column("bids", "ai_assessment")
