# app/models/satellite_analysis.py
import uuid
from datetime import datetime, date, timezone
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, Date, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.field import Field
    from app.models.anomaly import Anomaly


class SatelliteAnalysis(Base):
    __tablename__ = "satellite_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    field_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fields.id", ondelete="CASCADE"), nullable=False, index=True)
    image_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="sentinel-2")
    cloud_cover_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndvi_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    tiles_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raster_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # valid | discarded_cloud | processing | error
    status: Mapped[str] = mapped_column(String(30), default="processing")
    baseline_provisional: Mapped[bool] = mapped_column(default=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relacionamentos
    field: Mapped["Field"] = relationship("Field", back_populates="analyses")
    anomalies: Mapped[list["Anomaly"]] = relationship("Anomaly", back_populates="analysis")

    def __repr__(self) -> str:
        return f"<Analysis field={self.field_id} date={self.image_date} status={self.status}>"
