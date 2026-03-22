# app/models/field_inspection.py
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import Geometry

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.anomaly import Anomaly
    from app.models.user import User


class FieldInspection(Base):
    __tablename__ = "field_inspections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    anomaly_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("anomalies.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_issue: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # hora no celular
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relacionamentos
    anomaly: Mapped["Anomaly"] = relationship("Anomaly", back_populates="inspections")
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<FieldInspection anomaly={self.anomaly_id}>"
