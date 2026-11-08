"""Authentication and User Profile schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, EmailStr, Field

UserRole = Literal["student", "admin"]
SupportedLanguage = Literal["en", "ms"]


class UserProfile(BaseModel):
    id: str = Field(..., description="Supabase Auth user UUID")
    email: EmailStr
    display_name: str = Field(default="Student", min_length=1, max_length=120)
    role: UserRole = Field(default="student")
    preferred_language: SupportedLanguage = Field(default="en")
    created_at: datetime
    updated_at: datetime


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    preferred_language: SupportedLanguage | None = Field(default=None)


class DemoTokenRequest(BaseModel):
    role: UserRole = Field(default="student")
    preferred_language: SupportedLanguage = Field(default="en")


class DemoTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile

