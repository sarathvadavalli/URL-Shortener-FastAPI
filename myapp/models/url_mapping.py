from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from myapp.database import Base


class URLMapping(Base):
    __tablename__ = "url_mappings"

    # BigInteger because it has to store ids of more than 32-bits (~50-bits)
    url_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    original_url: Mapped[str] = mapped_column(String, nullable=False)
    short_code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    clicks: Mapped[list["Click"]] = relationship(
        back_populates="url_mapping",
        cascade="all, delete-orphan",
    )

    def __str__(self) -> str:
        return f"URLMapping(url_id={self.url_id!r}, short_code={self.short_code!r})"


class Click(Base):
    __tablename__ = "clicks"

    click_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url_mapping_id: Mapped[int] = mapped_column(ForeignKey("url_mappings.url_id"), nullable=False)
    clicked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    url_mapping: Mapped[URLMapping] = relationship(back_populates="clicks")

    def __str__(self) -> str:
        return f"Click(click_id={self.click_id!r}, short_code={self.url_mapping.short_code!r})"
