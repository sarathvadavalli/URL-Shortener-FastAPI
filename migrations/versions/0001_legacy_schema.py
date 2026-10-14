"""Baseline of the previously deployed schema.

An existing legacy database must be stamped 0001 before upgrading.
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("user_name", sa.String(20), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password", sa.String(100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("last_login_at", sa.DateTime),
    )
    op.create_table(
        "url_mappings",
        sa.Column(
            "url_id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("original_url", sa.String(2048), nullable=False),
        sa.Column("short_code", sa.String(10), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("click_count", sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
    )
    op.create_table(
        "clicks",
        sa.Column("click_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "url_mapping_id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            sa.ForeignKey("url_mappings.url_id"),
            nullable=False,
        ),
        sa.Column("clicked_at", sa.DateTime, nullable=False),
        sa.Column("user_agent", sa.String(255)),
        sa.Column("ip_address", sa.String(45)),
    )


def downgrade():
    raise RuntimeError(
        "Destructive downgrade disabled; restore a verified backup instead"
    )
