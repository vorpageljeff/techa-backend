"""add password reset codes table

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-30 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_codes",
        sa.Column("email", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=6), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("email"),
    )
    op.create_index(
        "ix_password_reset_codes_expires_at",
        "password_reset_codes",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_password_reset_codes_expires_at", table_name="password_reset_codes")
    op.drop_table("password_reset_codes")
