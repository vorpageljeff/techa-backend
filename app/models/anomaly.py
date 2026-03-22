# app/models/anomaly.py
# Anomalia detectada — núcleo do produto Techá
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, Float, Boolean, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import Geometry

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.field import Field
    from app.models.satellite_analysis import SatelliteAnalysis
    from app.models.field_inspection import FieldInspection


class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("satellite_analyses.id"), nullable=False)
    field_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fields.id"), nullable=False, index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ndvi_drop_pct: Mapped[float] = mapped_column(Float, nullable=False)       # ex: 18.5
    affected_area_ha: Mapped[float] = mapped_column(Float, nullable=False)
    # hidrico | praga | nutricional | unknown (IA de classificação em sprint futuro)
    suspected_type: Mapped[str] = mapped_column(String(50), default="unknown")
    # Zona afetada no mapa (MultiPolygon WGS84)
    geometry: Mapped[str | None] = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)
    # active | inspected | resolved
    status: Mapped[str] = mapped_column(String(30), default="active")
    push_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    alert_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relacionamentos
    field: Mapped["Field"] = relationship("Field", back_populates="anomalies")
    analysis: Mapped["SatelliteAnalysis"] = relationship("SatelliteAnalysis", back_populates="anomalies")
    inspections: Mapped[list["FieldInspection"]] = relationship("FieldInspection", back_populates="anomaly")

    __table_args__ = (
        Index("anomalies_geometry_idx", "geometry", postgresql_using="gist"),
    )

    def __repr__(self) -> str:
        return f"<Anomaly drop={self.ndvi_drop_pct:.1f}% area={self.affected_area_ha:.1f}ha status={self.status}>"
