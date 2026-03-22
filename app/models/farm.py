# app/models/farm.py
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.field import Field


class Farm(Base):
    __tablename__ = "farms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)        # área total da fazenda
    crop: Mapped[str | None] = mapped_column(String(100), nullable=True)       # cultura principal
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relacionamentos
    user: Mapped["User"] = relationship("User", back_populates="farms")
    fields: Mapped[list["Field"]] = relationship("Field", back_populates="farm", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Farm '{self.name}' | {self.area_ha}ha>"
