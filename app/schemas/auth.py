# app/schemas/auth.py
# Schemas Pydantic para autenticação — request e response

from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator
from uuid import UUID


class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Senha deve ter ao menos 8 caracteres")
        return v

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nome não pode ser vazio")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: UUID
    name: str
    email: str
    plan: str
    is_active: bool
    must_change_password: bool = False
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}
