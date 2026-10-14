from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from myapp.core.time import utcnow
from myapp.database import Base

# SQLite needs INTEGER exactly for auto-increment. MySQL retains BIGINT.
ID_TYPE = BigInteger().with_variant(Integer, "sqlite")
PRECISE_DATETIME = DateTime().with_variant(DATETIME(fsp=6), "mysql")
CODE_TYPE = String(11).with_variant(String(11, collation="ascii_bin"), "mysql")


class URLMapping(Base):
    __tablename__ = "url_mappings"
    __table_args__ = (
        UniqueConstraint("owner_key", "url_hash", name="uq_url_owner_hash"),
    )

    url_id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # Guests are scoped to a random signed-session identity; no fictitious user 0.
    owner_key: Mapped[str] = mapped_column(String(80), nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    original_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # NULL exists only during the insert/flush that obtains the database ID.
    short_code: Mapped[str | None] = mapped_column(
        CODE_TYPE, unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    clicks: Mapped[list["Click"]] = relationship(
        back_populates="url_mapping", cascade="all, delete-orphan"
    )


class Click(Base):
    __tablename__ = "clicks"
    click_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url_mapping_id: Mapped[int] = mapped_column(
        ForeignKey("url_mappings.url_id"), nullable=False
    )
    clicked_at: Mapped[datetime] = mapped_column(
        PRECISE_DATETIME, default=utcnow, nullable=False
    )
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    url_mapping: Mapped[URLMapping] = relationship(back_populates="clicks")


class CreationRequest(Base):
    """Transactional idempotency ledger; only completed results are committed."""

    __tablename__ = "creation_requests"
    owner_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    request_key: Mapped[str] = mapped_column(String(36), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        PRECISE_DATETIME, nullable=False, index=True
    )
    url_mapping_id: Mapped[int | None] = mapped_column(
        ForeignKey("url_mappings.url_id", ondelete="CASCADE")
    )
