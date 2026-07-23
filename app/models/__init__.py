# app/models/__init__.py
# Importa todos os models para que o Alembic os detecte automaticamente

from app.models.admin_audit_log import AdminAuditLog
from app.models.anomaly import Anomaly
from app.models.farm import Farm
from app.models.field import Field
from app.models.field_inspection import FieldInspection
from app.models.password_reset import PasswordResetCode
from app.models.satellite_analysis import SatelliteAnalysis
from app.models.user import User

__all__ = [
    "AdminAuditLog",
    "Anomaly",
    "Farm",
    "Field",
    "FieldInspection",
    "PasswordResetCode",
    "SatelliteAnalysis",
    "User",
]
