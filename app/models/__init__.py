# app/models/__init__.py
# Importa todos os models para que o Alembic os detecte automaticamente

from app.models.user import User
from app.models.farm import Farm
from app.models.field import Field
from app.models.satellite_analysis import SatelliteAnalysis
from app.models.anomaly import Anomaly
from app.models.field_inspection import FieldInspection

__all__ = [
    "User",
    "Farm",
    "Field",
    "SatelliteAnalysis",
    "Anomaly",
    "FieldInspection",
]
