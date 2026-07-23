# tests/unit/test_security.py
# Testes unitários para autenticação JWT e hashing de senhas
# Execute: pytest tests/unit/test_security.py -v

import pytest
from uuid import uuid4
from unittest.mock import patch

# Mock settings para não precisar do .env nos testes
import os
os.environ.update({
    "SECRET_KEY": "test_secret_key_very_long_and_random",
    "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/test",
    "DATABASE_URL_SYNC": "postgresql://u:p@localhost/test",
    "JWT_SECRET_KEY": "test_jwt_secret_key_also_very_long",
    "COPERNICUS_CLIENT_ID": "test_id",
    "COPERNICUS_CLIENT_SECRET": "test_secret",
})

from app.core.security import (
    generate_temporary_password,
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)


class TestPasswordHashing:
    def test_temporary_password_is_strong_and_random(self):
        first = generate_temporary_password()
        second = generate_temporary_password()

        assert first.startswith("Tmp-")
        assert len(first) >= 20
        assert first != second
        assert verify_password(first, hash_password(first)) is True

    def test_hash_password_returns_string(self):
        result = hash_password("minha_senha_123")
        assert isinstance(result, str)
        assert len(result) > 20

    def test_hash_is_not_plain_text(self):
        plain = "senha_secreta"
        hashed = hash_password(plain)
        assert hashed != plain

    def test_verify_correct_password(self):
        plain = "senha_correta_456"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("senha_original")
        assert verify_password("senha_errada", hashed) is False

    def test_same_password_generates_different_hashes(self):
        """bcrypt usa salt aleatório — dois hashes da mesma senha devem ser diferentes"""
        h1 = hash_password("mesma_senha")
        h2 = hash_password("mesma_senha")
        assert h1 != h2
        # Mas ambos devem ser verificáveis
        assert verify_password("mesma_senha", h1) is True
        assert verify_password("mesma_senha", h2) is True


class TestJWT:
    def test_create_token_returns_string(self):
        user_id = uuid4()
        token = create_access_token(user_id)
        assert isinstance(token, str)
        assert len(token) > 50

    def test_decode_valid_token(self):
        user_id = uuid4()
        token = create_access_token(user_id)
        payload = decode_access_token(token)
        assert payload["user_id"] == str(user_id)

    def test_decode_invalid_token_raises(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            decode_access_token("token.invalido.aqui")
        assert exc.value.status_code == 401

    def test_decode_expired_token_raises(self):
        from datetime import timedelta
        from fastapi import HTTPException
        user_id = uuid4()
        # Token que expirou há 1 segundo
        token = create_access_token(user_id, expires_delta=timedelta(seconds=-1))
        with pytest.raises(HTTPException) as exc:
            decode_access_token(token)
        assert exc.value.status_code == 401
