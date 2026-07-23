import pytest
from pydantic import ValidationError

from app.schemas.admin import AdminBootstrapRequest


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
