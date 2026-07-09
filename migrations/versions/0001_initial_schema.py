"""initial schema — users, farms, fields, satellite_analyses, anomalies, field_inspections

Revision ID: 0001
Revises:
Create Date: 2026-03-23 00:00:00.000000

Nota: geometria armazenada como WKT (Text) para compatibilidade com
PostgreSQL padrão. PostGIS pode ser adicionado futuramente para
queries espaciais avançadas.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extensões necessárias no Postgres gerenciado ──────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS postgis;')
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    # ── users ─────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(200), nullable=False),
        sa.Column("password", sa.String(200), nullable=False),
        sa.Column("plan", sa.String(20), nullable=False, server_default="free"),
        sa.Column("fcm_token", sa.String(300), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── farms ─────────────────────────────────────────────────────
    op.create_table(
        "farms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("area_ha", sa.Float(), nullable=True),
        sa.Column("crop", sa.String(100), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_farms_user_id", "farms", ["user_id"])

    # ── fields ────────────────────────────────────────────────────
    # geometry armazenada como WKT (ex: "POLYGON((lon lat, ...))")
    op.create_table(
        "fields",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("crop", sa.String(100), nullable=True),
        sa.Column("planting_date", sa.Date(), nullable=True),
        sa.Column("geometry", sa.Text(), nullable=False),
        sa.Column("area_ha", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["farm_id"], ["farms.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_fields_farm_id", "fields", ["farm_id"])

    # ── satellite_analyses ────────────────────────────────────────
    op.create_table(
        "satellite_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("field_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("image_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="sentinel-2"),
        sa.Column("cloud_cover_pct", sa.Float(), nullable=True),
        sa.Column("ndvi_mean", sa.Float(), nullable=True),
        sa.Column("ndvi_min", sa.Float(), nullable=True),
        sa.Column("ndvi_max", sa.Float(), nullable=True),
        sa.Column("tiles_path", sa.String(500), nullable=True),
        sa.Column("raster_path", sa.String(500), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="processing"),
        sa.Column("baseline_provisional", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["field_id"], ["fields.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_satellite_analyses_field_id", "satellite_analyses", ["field_id"])

    # ── anomalies ─────────────────────────────────────────────────
    # geometry armazenada como WKT (ex: "MULTIPOLYGON(...)")
    op.create_table(
        "anomalies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ndvi_drop_pct", sa.Float(), nullable=False),
        sa.Column("affected_area_ha", sa.Float(), nullable=False),
        sa.Column("suspected_type", sa.String(50), nullable=False, server_default="unknown"),
        sa.Column("geometry", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("push_sent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("alert_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["analysis_id"], ["satellite_analyses.id"]),
        sa.ForeignKeyConstraint(["field_id"], ["fields.id"]),
    )
    op.create_index("ix_anomalies_field_id", "anomalies", ["field_id"])

    # ── field_inspections ─────────────────────────────────────────
    # location armazenada como WKT (ex: "POINT(lon lat)")
    op.create_table(
        "field_inspections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("anomaly_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("photo_url", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("confirmed_issue", sa.String(100), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["anomaly_id"], ["anomalies.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_field_inspections_anomaly_id", "field_inspections", ["anomaly_id"])


def downgrade() -> None:
    op.drop_table("field_inspections")
    op.drop_table("anomalies")
    op.drop_table("satellite_analyses")
    op.drop_table("fields")
    op.drop_table("farms")
    op.drop_table("users")
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp";')
    op.execute('DROP EXTENSION IF EXISTS postgis;')
