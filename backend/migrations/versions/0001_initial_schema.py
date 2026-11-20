"""Create the initial BharatSetu schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

from app.db.database import Base
from app.models import models  # noqa: F401 - populate metadata

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    # Bring databases created by the previous SQLite startup migration up to
    # the current model without requiring data export or table recreation.
    inspector = sa.inspect(bind)
    additions = {
        "verifications": {"provider_mode": sa.Column("provider_mode", sa.String(), nullable=False, server_default="MOCK")},
        "tenders": {"estimated_value": sa.Column("estimated_value", sa.Float(), nullable=False, server_default="0.0")},
        "rule_results": {"verification_id": sa.Column("verification_id", sa.String(), nullable=True)},
        "notifications": {
            "channel": sa.Column("channel", sa.String(), nullable=False, server_default="IN_APP"),
            "delivery_status": sa.Column("delivery_status", sa.String(), nullable=False, server_default="SENT"),
            "provider_reference": sa.Column("provider_reference", sa.String(), nullable=True),
            "failure_reason": sa.Column("failure_reason", sa.Text(), nullable=True),
        },
    }
    for table, columns in additions.items():
        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, column in columns.items():
            if name not in existing:
                op.add_column(table, column)


def downgrade():
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
