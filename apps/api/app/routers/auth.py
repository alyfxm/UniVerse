"""Authentication and User Profile endpoints (`/api/v1/auth`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthorizationError
from app.core.security import create_supabase_jwt, get_current_user
from app.models.auth import (
    DemoTokenRequest,
    DemoTokenResponse,
    UpdateProfileRequest,
    UserProfile,
)
from app.repositories.profile_repo import ProfileRepository, get_profile_repository

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/me", response_model=UserProfile)
async def get_my_profile(
    current_user: UserProfile = Depends(get_current_user),
) -> UserProfile:
    """Verify Supabase JWT and return the authenticated user's profile and role."""
    return current_user


@router.patch("/me", response_model=UserProfile)
async def update_my_profile(
    payload: UpdateProfileRequest,
    current_user: UserProfile = Depends(get_current_user),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
) -> UserProfile:
    """Update the authenticated user's display name or preferred language (`en` | `ms`)."""
    return profile_repo.update_profile(
        user_id=current_user.id,
        current_profile=current_user,
        update_req=payload,
    )


@router.post("/demo-token", response_model=DemoTokenResponse)
async def issue_demo_token(
    payload: DemoTokenRequest,
    settings: Settings = Depends(get_settings),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
) -> DemoTokenResponse:
    """Issue a signed local development JWT for Student or Admin testing when APP_ENV != production."""
    if settings.APP_ENV == "production":
        raise AuthorizationError("Demo tokens are disabled in production.")

    if payload.role == "admin":
        user_id = "99999999-9999-9999-9999-999999999999"
        email = "admin@universe.edu.my"
        display_name = "Dr.Farah (Campus Admin)"
    else:
        user_id = "11111111-1111-1111-1111-111111111111"
        email = "aiman.hakim@student.universe.edu.my"
        display_name = "Aiman Hakim"

    profile = profile_repo.get_or_create_profile(
        user_id=user_id,
        email=email,
        display_name=display_name,
        app_role=payload.role,
        preferred_language=payload.preferred_language,
    )
    token = create_supabase_jwt(
        user_id=profile.id,
        email=profile.email,
        role=profile.role,
        display_name=profile.display_name,
        preferred_language=profile.preferred_language,
    )
    return DemoTokenResponse(access_token=token, user=profile)

