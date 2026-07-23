import pytest
from pydantic import ValidationError

from app.schemas.admin import AdminBootstrapRequest
from app.schemas.auth import UserResponse


def test_admin_bootstrap_accepts_strong_temporary_password() -> None:
    payload = AdminBootstrapRequest(
        name="Administrador Techá",
        email="admin@techa.com.py",
        password="Temp-Segura-2026",
    )

    assert payload.email == "admin@techa.com.py"


def test_admin_bootstrap_rejects_short_password() -> None:
    with pytest.raises(ValidationError):
        AdminBootstrapRequest(
            name="Administrador Techá",
            email="admin@techa.com.py",
            password="admin",
        )


def test_admin_user_response_accepts_login_timestamp() -> None:
    payload = UserResponse(
        id="9c8c844d-74d6-48f3-8868-5a5440b0d894",
        name="Administrador Techá",
        email="admin@techa.com.py",
        plan="admin",
        is_active=True,
        must_change_password=True,
        last_login_at="2026-07-23T17:11:44Z",
    )

    assert payload.last_login_at is not None
