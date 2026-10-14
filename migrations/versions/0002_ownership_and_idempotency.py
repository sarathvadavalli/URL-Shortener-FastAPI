"""Guest ownership, bounded unique URL fingerprints, durable idempotency.

Preflight refuses existing duplicates rather than deleting links or click history.
"""

import hashlib

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME

revision = "0002"
down_revision = "0001"


def upgrade():
    conn = op.get_bind()
    seen = set()
    # Stream rather than load every URL into memory; retain only uniqueness keys.
    for row in conn.execute(
        sa.text("SELECT url_id, user_id, original_url FROM url_mappings")
    ):
        owner = f"u:{row.user_id}" if row.user_id else "legacy:guest"
        digest = hashlib.sha256(row.original_url.encode("utf-8")).hexdigest()
        key = (owner, digest)
        if key in seen:
            raise RuntimeError(
                "Duplicate owner/URL rows exist; reconcile them manually before upgrading. No URLs were deleted."
            )
        seen.add(key)
    with op.batch_alter_table("url_mappings") as batch:
        batch.add_column(sa.Column("owner_key", sa.String(80), nullable=True))
        batch.add_column(sa.Column("url_hash", sa.String(64), nullable=True))
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=True)
        code_type = (
            sa.String(11, collation="ascii_bin")
            if conn.dialect.name == "mysql"
            else sa.String(11)
        )
        batch.alter_column(
            "short_code", existing_type=sa.String(10), type_=code_type, nullable=True
        )
    for row in conn.execute(
        sa.text("SELECT url_id, user_id, original_url FROM url_mappings")
    ):
        conn.execute(
            sa.text(
                "UPDATE url_mappings SET owner_key=:owner, url_hash=:hash, user_id=:user WHERE url_id=:id"
            ),
            {
                "owner": f"u:{row.user_id}" if row.user_id else "legacy:guest",
                "hash": hashlib.sha256(row.original_url.encode("utf-8")).hexdigest(),
                "user": row.user_id or None,
                "id": row.url_id,
            },
        )
    with op.batch_alter_table("url_mappings") as batch:
        batch.alter_column("owner_key", existing_type=sa.String(80), nullable=False)
        batch.alter_column("url_hash", existing_type=sa.String(64), nullable=False)
        batch.create_unique_constraint("uq_url_owner_hash", ["owner_key", "url_hash"])
    if conn.dialect.name == "mysql":
        op.alter_column(
            "clicks",
            "clicked_at",
            existing_type=sa.DateTime(),
            type_=DATETIME(fsp=6),
            existing_nullable=False,
        )
    op.create_table(
        "creation_requests",
        sa.Column("owner_key", sa.String(80), primary_key=True),
        sa.Column("request_key", sa.String(36), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime().with_variant(DATETIME(fsp=6), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "url_mapping_id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            sa.ForeignKey("url_mappings.url_id", ondelete="CASCADE"),
        ),
    )
    op.create_index(
        "ix_creation_requests_expires_at", "creation_requests", ["expires_at"]
    )


def downgrade():
    raise RuntimeError(
        "Guest ownership cannot be safely downgraded; restore a verified backup"
    )
