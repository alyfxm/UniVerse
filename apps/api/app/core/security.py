"""Supabase JWT verification and Role-Based Access Control (RBAC) dependencies.

Follows Supabase security guidelines:
- Never trusts `user_metadata` for authorization decisions (`role`).
- Reads authorization role only from `public.profiles` (or initial `app_metadata` on profile creation).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.models.auth import SupportedLanguage, UserProfile, UserRole
from app.repositories.profile_repo import ProfileRepository, get_profile_repository

bearer_scheme = HTTPBearer(auto_error=False)


def create_supabase_jwt(
    user_id: str,
    email: str,
    role: UserRole = "student",
    display_name: str | None = None,
    preferred_language: SupportedLanguage = "en",
    secret: str | None = None,
    expires_delta: timedelta = timedelta(hours=2),
) -> str:
    """Create a signed Supabase-compatible JWT (used for local dev & automated tests)."""
    settings = get_settings()
    jwt_secret = secret or settings.SUPABASE_JWT_SECRET
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "aud": "authenticated",
        "role": "authenticated",
        "app_metadata": {"role": role, "provider": "email"},
        "user_metadata": {
            "display_name": display_name or email.split("@")[0],
            "preferred_language": preferred_language,
        },
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


def decode_and_verify_supabase_jwt(token: str, settings: Settings) -> dict[str, Any]:
    """Decode and validate a Supabase JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Invalid authentication token.") from exc

    sub = payload.get("sub")
    email = payload.get("email")
    if not sub or not isinstance(sub, str):
        raise AuthenticationError("Token payload is missing required 'sub' subject claim.")
    if not email or not isinstance(email, str):
        raise AuthenticationError("Token payload is missing required 'email' claim.")

    return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
) -> UserProfile:
    """FastAPI dependency that verifies Bearer JWT and returns the user's Profile."""
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing Bearer authentication token.")

    payload = decode_and_verify_supabase_jwt(credentials.credentials, settings)

    user_id: str = payload["sub"]
    email: str = payload["email"]

    # SECURITY: Never read role from user_metadata (user-editable in Supabase).
    # Only allow app_metadata.role as initial seed if profile is newly created.
    app_metadata = payload.get("app_metadata") or {}
    raw_app_role = app_metadata.get("role", "student")
    app_role: UserRole = "admin" if raw_app_role == "admin" else "student"

    user_metadata = payload.get("user_metadata") or {}
    display_name = user_metadata.get("display_name")
    raw_lang = user_metadata.get("preferred_language", "en")
    preferred_lang: SupportedLanguage = "ms" if raw_lang == "ms" else "en"

    return profile_repo.get_or_create_profile(
        user_id=user_id,
        email=email,
        display_name=display_name,
        app_role=app_role,
        preferred_language=preferred_lang,
    )


async def require_admin(
    current_user: UserProfile = Depends(get_current_user),
) -> UserProfile:
    """FastAPI dependency enforcing `admin` role on protected admin routes."""
    if current_user.role != "admin":
        raise AuthorizationError(
            message="Administrator privileges are required to access this resource.",
            details={"required_role": "admin", "current_role": current_user.role},
        )
    return current_user

