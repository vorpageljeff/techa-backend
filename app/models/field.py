# app/models/field.py
# Talhão — contém o polígono geoespacial (PostGIS)
import uuid
from datetime import datetime, date, timezone
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, Date, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.farm import Farm
    from app.models.satellite_analysis import SatelliteAnalysis
    from app.models.anomaly import Anomaly


class Field(Base):
    __tablename__ = "fields"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    crop: Mapped[str | None] = mapped_column(String(100), nullable=True)   # soja | milho | trigo
    planting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Polígono WGS84 — armazenado como WKT (ex: "POLYGON((lon lat, ...))")
    # PostGIS pode ser adicionado futuramente para queries espaciais
    geometry: Mapped[str] = mapped_column(Text, nullable=False)
    area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)    # calculado do polígono
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relacionamentos
    farm: Mapped["Farm"] = relationship("Farm", back_populates="fields")
    analyses: Mapped[list["SatelliteAnalysis"]] = relationship("SatelliteAnalysis", back_populates="field", cascade="all, delete-orphan")
    anomalies: Mapped[list["Anomaly"]] = relationship("Anomaly", back_populates="field", cascade="all, delete-orphan")

    # Índice padrão na geometria (GIST será adicionado quando migrar para PostGIS)
    __table_args__ = ()

    def __repr__(self) -> str:
        return f"<Field '{self.name}' | {self.area_ha:.1f}ha>"
