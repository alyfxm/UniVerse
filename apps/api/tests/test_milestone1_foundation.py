"""Unit and Integration Tests for Milestone 1:
- Configuration & environment validation
- Standardized RFC 7807 error envelopes & correlation ID headers
- Supabase JWT verification (valid, expired, tampered, missing claims)
- Security: Untrusted `user_metadata.role` privilege escalation prevention
- RBAC enforcement (`get_current_user` vs `require_admin`)
- `/api/v1/health` and `/api/v1/auth/me` endpoints
"""

from __future__ import annotations

from datetime import timedelta
import httpx
import jwt
import pytest
from fastapi import Depends, FastAPI

from app.core.config import Settings, get_settings
from app.core.security import create_supabase_jwt, require_admin
from app.main import create_app
from app.models.auth import UserProfile
from app.repositories.profile_repo import ProfileRepository, get_profile_repository


@pytest.fixture
def test_app() -> FastAPI:
    app = create_app()
    repo = ProfileRepository()
    app.dependency_overrides[get_profile_repository] = lambda: repo

    @app.get("/api/v1/admin/test-only", response_model=UserProfile)
    async def admin_only_probe(admin_user: UserProfile = Depends(require_admin)) -> UserProfile:
        return admin_user

    return app


@pytest.fixture
async def client(test_app: FastAPI):
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


def test_settings_validation() -> None:
    """Verify Settings validates API prefix and computes derived properties."""
    s = Settings(
        API_V1_PREFIX="/api/v1/",
        CORS_ORIGINS="http://localhost:3000, https://universe.edu.my",
        MAX_UPLOAD_SIZE_MB=20,
    )
    assert s.API_V1_PREFIX == "/api/v1"
    assert s.cors_origins_list == ["http://localhost:3000", "https://universe.edu.my"]
    assert s.max_upload_size_bytes == 20 * 1024 * 1024

    with pytest.raises(ValueError, match="API_V1_PREFIX must start with '/'"):
        Settings(API_V1_PREFIX="api/v1")


async def test_health_endpoint_and_correlation_id(client: httpx.AsyncClient) -> None:
    """Verify `/api/v1/health` returns 200 OK and preserves X-Request-ID."""
    custom_req_id = "req_milestone1_check"
    response = await client.get("/api/v1/health", headers={"X-Request-ID": custom_req_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_req_id

    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "UniVerse API"
    assert "supabase" in data["dependencies"]
    assert "chromadb" in data["dependencies"]
    assert "gemini" in data["dependencies"]


async def test_auth_me_requires_bearer_token(client: httpx.AsyncClient) -> None:
    """Verify unauthenticated request returns 401 with standard error envelope."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "AUTHENTICATION_FAILED"
    assert "request_id" in body["error"]


async def test_auth_me_rejects_expired_and_invalid_tokens(client: httpx.AsyncClient) -> None:
    """Verify expired or malformed JWT tokens are rejected with 401."""
    expired_token = create_supabase_jwt(
        user_id="11111111-1111-1111-1111-111111111111",
        email="student@universe.edu.my",
        expires_delta=timedelta(seconds=-10),
    )
    res_expired = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert res_expired.status_code == 401
    assert "expired" in res_expired.json()["error"]["message"].lower()

    wrong_secret_token = create_supabase_jwt(
        user_id="11111111-1111-1111-1111-111111111111",
        email="student@universe.edu.my",
        secret="wrong-secret-key-that-does-not-match-32b",
    )
    res_wrong = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {wrong_secret_token}"},
    )
    assert res_wrong.status_code == 401


async def test_user_metadata_role_escalation_is_blocked(client: httpx.AsyncClient) -> None:
    """Verify a token with `user_metadata.role = 'admin'` cannot escalate privileges."""
    settings = get_settings()
    forged_payload = {
        "sub": "22222222-2222-2222-2222-222222222222",
        "email": "clever.student@universe.edu.my",
        "aud": "authenticated",
        "role": "authenticated",
        "app_metadata": {"role": "student"},
        # Attempting to self-assign admin in user_metadata
        "user_metadata": {"role": "admin", "display_name": "Aiman"},
    }
    token = jwt.encode(forged_payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["role"] == "student"

    # Attempting to call admin-only endpoint must return 403
    res_admin = await client.get(
        "/api/v1/admin/test-only",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_admin.status_code == 403
    assert res_admin.json()["error"]["code"] == "PERMISSION_DENIED"


async def test_profile_sync_and_update_flow(client: httpx.AsyncClient) -> None:
    """Verify student profile creation, PATCH update (`en` -> `ms`), and validation."""
    token = create_supabase_jwt(
        user_id="33333333-3333-3333-3333-333333333333",
        email="nurul@universe.edu.my",
        role="student",
        display_name="Nurul Izzah",
        preferred_language="en",
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Initial profile fetch
    get_res = await client.get("/api/v1/auth/me", headers=headers)
    assert get_res.status_code == 200
    profile = get_res.json()
    assert profile["id"] == "33333333-3333-3333-3333-333333333333"
    assert profile["display_name"] == "Nurul Izzah"
    assert profile["preferred_language"] == "en"
    assert profile["role"] == "student"

    # Update preferred_language to Malay ('ms')
    patch_res = await client.patch(
        "/api/v1/auth/me",
        headers=headers,
        json={"display_name": "Nurul Izzah Binti Ahmad", "preferred_language": "ms"},
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["display_name"] == "Nurul Izzah Binti Ahmad"
    assert updated["preferred_language"] == "ms"

    # Invalid language code rejected with 422 VALIDATION_ERROR
    invalid_res = await client.patch(
        "/api/v1/auth/me",
        headers=headers,
        json={"preferred_language": "fr"},
    )
    assert invalid_res.status_code == 422
    assert invalid_res.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_admin_rbac_allows_admin_user(client: httpx.AsyncClient) -> None:
    """Verify user with `app_metadata.role = 'admin'` passes `require_admin` guard."""
    admin_token = create_supabase_jwt(
        user_id="99999999-9999-9999-9999-999999999999",
        email="admin@universe.edu.my",
        role="admin",
        display_name="Campus Admin",
    )
    res = await client.get(
        "/api/v1/admin/test-only",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert res.json()["role"] == "admin"

