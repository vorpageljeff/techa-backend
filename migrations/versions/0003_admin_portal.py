"""add admin portal security and audit fields

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE users SET must_change_password = true WHERE plan = 'admin'"
    )
    op.execute(
        """
        UPDATE users
        SET
            name = 'Administrador Techá',
            password = '$2b$12$4Q/Ex8ilBhy6qsC1kvQg/uVtdmYia173.BH.Q6zb8e9kRUNArydyG',
            plan = 'admin',
            is_active = true,
            must_change_password = true
        WHERE lower(email) = 'admin@techa.com.py'
          AND NOT EXISTS (SELECT 1 FROM users WHERE plan = 'admin')
        """
    )
    op.execute(
        """
        INSERT INTO users (
            id,
            name,
            email,
            password,
            plan,
            is_active,
            must_change_password,
            created_at
        )
        SELECT
            uuid_generate_v4(),
            'Administrador Techá',
            'admin@techa.com.py',
            '$2b$12$4Q/Ex8ilBhy6qsC1kvQg/uVtdmYia173.BH.Q6zb8e9kRUNArydyG',
            'admin',
            true,
            true,
            now()
        WHERE NOT EXISTS (SELECT 1 FROM users WHERE plan = 'admin')
        """
    )

    op.create_table(
        "admin_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(length=200), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.String(length=120), nullable=True),
        sa.Column(
            "details",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_audit_logs_actor_user_id",
        "admin_audit_logs",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_admin_audit_logs_action",
        "admin_audit_logs",
        ["action"],
    )
    op.create_index(
        "ix_admin_audit_logs_created_at",
        "admin_audit_logs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_audit_logs_created_at",
        table_name="admin_audit_logs",
    )
    op.drop_index(
        "ix_admin_audit_logs_action",
        table_name="admin_audit_logs",
    )
    op.drop_index(
        "ix_admin_audit_logs_actor_user_id",
        table_name="admin_audit_logs",
    )
    op.drop_table("admin_audit_logs")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "must_change_password")
