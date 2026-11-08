"""Repository for managing user profiles in Supabase PostgreSQL (with local fallback)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import Settings, get_settings
from app.models.auth import SupportedLanguage, UpdateProfileRequest, UserProfile, UserRole


class ProfileRepository:
    """Data access layer for `public.profiles`."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._local_profiles: dict[str, UserProfile] = {}
        self._supabase_client: Any = None
        if self.settings.is_supabase_configured:
            try:
                from supabase import create_client

                self._supabase_client = create_client(
                    self.settings.SUPABASE_URL,
                    self.settings.SUPABASE_SERVICE_ROLE_KEY,
                )
            except Exception:
                self._supabase_client = None

    def get_or_create_profile(
        self,
        user_id: str,
        email: str,
        display_name: str | None = None,
        app_role: UserRole = "student",
        preferred_language: SupportedLanguage = "en",
    ) -> UserProfile:
        """Fetch user profile from Supabase or create it if not yet synced."""
        resolved_name = (display_name or email.split("@")[0] or "Student").strip()

        if self._supabase_client is not None:
            response = (
                self._supabase_client.table("profiles")
                .select("*")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            rows = response.data or []
            if rows:
                row = rows[0]
                return UserProfile(
                    id=str(row["id"]),
                    email=row["email"],
                    display_name=row.get("display_name") or resolved_name,
                    role=row.get("role", "student"),
                    preferred_language=row.get("preferred_language", "en"),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )

            now_iso = datetime.now(timezone.utc).isoformat()
            insert_payload = {
                "id": user_id,
                "email": email,
                "display_name": resolved_name,
                "role": app_role,
                "preferred_language": preferred_language,
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            inserted = (
                self._supabase_client.table("profiles")
                .upsert(insert_payload)
                .execute()
            )
            row = (inserted.data or [insert_payload])[0]
            return UserProfile(
                id=str(row["id"]),
                email=row["email"],
                display_name=row.get("display_name") or resolved_name,
                role=row.get("role", app_role),
                preferred_language=row.get("preferred_language", preferred_language),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

        # Local fallback store
        if user_id in self._local_profiles:
            return self._local_profiles[user_id]

        now = datetime.now(timezone.utc)
        profile = UserProfile(
            id=user_id,
            email=email,
            display_name=resolved_name,
            role=app_role,
            preferred_language=preferred_language,
            created_at=now,
            updated_at=now,
        )
        self._local_profiles[user_id] = profile
        return profile

    def update_profile(
        self,
        user_id: str,
        current_profile: UserProfile,
        update_req: UpdateProfileRequest,
    ) -> UserProfile:
        """Update allowed user profile fields (`display_name`, `preferred_language`)."""
        new_display_name = (
            update_req.display_name.strip()
            if update_req.display_name is not None
            else current_profile.display_name
        )
        new_lang = (
            update_req.preferred_language
            if update_req.preferred_language is not None
            else current_profile.preferred_language
        )
        now = datetime.now(timezone.utc)

        if self._supabase_client is not None:
            response = (
                self._supabase_client.table("profiles")
                .update(
                    {
                        "display_name": new_display_name,
                        "preferred_language": new_lang,
                        "updated_at": now.isoformat(),
                    }
                )
                .eq("id", user_id)
                .execute()
            )
            rows = response.data or []
            if rows:
                row = rows[0]
                return UserProfile(
                    id=str(row["id"]),
                    email=row["email"],
                    display_name=row.get("display_name") or new_display_name,
                    role=row.get("role", current_profile.role),
                    preferred_language=row.get("preferred_language", new_lang),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )

        updated = current_profile.model_copy(
            update={
                "display_name": new_display_name,
                "preferred_language": new_lang,
                "updated_at": now,
            }
        )
        self._local_profiles[user_id] = updated
        return updated


_profile_repo_instance: ProfileRepository | None = None


def get_profile_repository() -> ProfileRepository:
    """FastAPI dependency returning singleton ProfileRepository."""
    global _profile_repo_instance
    if _profile_repo_instance is None:
        _profile_repo_instance = ProfileRepository()
    return _profile_repo_instance

