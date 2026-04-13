"""Auth request/response schemas."""

from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: Optional[str] = Field(default=None, max_length=255)
    org_name: Optional[str] = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: Optional[str]
    org_id: Optional[uuid.UUID]
    org_name: Optional[str]

    model_config = {"from_attributes": True}


TokenResponse.model_rebuild()
