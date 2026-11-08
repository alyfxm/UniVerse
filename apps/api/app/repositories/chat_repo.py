"""Repository for managing `chat_sessions` and `messages` in Supabase PostgreSQL (with local fallback)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
import uuid

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthorizationError, ResourceNotFoundError
from app.models.chat import (
    CategoryFilter,
    ChatMessage,
    ChatSessionDetail,
    ChatSessionSummary,
    Citation,
    DetectedLanguage,
    MessageRole,
)


class ChatRepository:
    """Data access layer for `public.chat_sessions` and `public.messages`."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._local_sessions: dict[str, ChatSessionSummary] = {}
        self._local_messages: dict[str, ChatMessage] = {}
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

    def create_session(
        self,
        user_id: str,
        title: str,
        language: DetectedLanguage = "en",
        category_filter: CategoryFilter = "all",
        session_id: str | None = None,
    ) -> ChatSessionSummary:
        """Create a new chat session for a user."""
        sid = session_id or str(uuid.uuid4())
        clean_title = (title.strip()[:80] or "New Conversation")
        now = datetime.now(timezone.utc)

        session = ChatSessionSummary(
            id=sid,
            user_id=user_id,
            title=clean_title,
            language=language,
            category_filter=category_filter,
            is_archived=False,
            created_at=now,
            updated_at=now,
        )

        if self._supabase_client is not None:
            payload = {
                "id": session.id,
                "user_id": session.user_id,
                "title": session.title,
                "language": session.language,
                "category_filter": session.category_filter,
                "is_archived": session.is_archived,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            res = self._supabase_client.table("chat_sessions").insert(payload).execute()
            rows = res.data or [payload]
            return self._row_to_session(rows[0])

        self._local_sessions[sid] = session
        return session

    def get_session(self, session_id: str, user_id: str) -> ChatSessionSummary:
        """Fetch a session and verify ownership."""
        if self._supabase_client is not None:
            res = (
                self._supabase_client.table("chat_sessions")
                .select("*")
                .eq("id", session_id)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            if not rows:
                raise ResourceNotFoundError("ChatSession", session_id)
            session = self._row_to_session(rows[0])
            if session.user_id != user_id:
                raise AuthorizationError("You do not have access to this chat session.")
            return session

        if session_id not in self._local_sessions:
            raise ResourceNotFoundError("ChatSession", session_id)
        session = self._local_sessions[session_id]
        if session.user_id != user_id:
            raise AuthorizationError("You do not have access to this chat session.")
        return session

    def get_or_create_session(
        self,
        session_id: str | None,
        user_id: str,
        first_query: str,
        language: DetectedLanguage = "en",
        category_filter: CategoryFilter = "all",
    ) -> ChatSessionSummary:
        """Return existing session if owned by user, or create a new one titled from `first_query`."""
        if session_id:
            try:
                return self.get_session(session_id=session_id, user_id=user_id)
            except ResourceNotFoundError:
                return self.create_session(
                    user_id=user_id,
                    title=first_query[:80],
                    language=language,
                    category_filter=category_filter,
                    session_id=session_id,
                )
        return self.create_session(
            user_id=user_id,
            title=first_query[:80],
            language=language,
            category_filter=category_filter,
        )

    def list_user_sessions(
        self,
        user_id: str,
        include_archived: bool = False,
    ) -> list[ChatSessionSummary]:
        """List a user's chat sessions ordered by `updated_at DESC`."""
        if self._supabase_client is not None:
            query = (
                self._supabase_client.table("chat_sessions")
                .select("*")
                .eq("user_id", user_id)
            )
            if not include_archived:
                query = query.eq("is_archived", False)
            res = query.order("updated_at", desc=True).execute()
            return [self._row_to_session(r) for r in (res.data or [])]

        sessions = [
            s
            for s in self._local_sessions.values()
            if s.user_id == user_id and (include_archived or not s.is_archived)
        ]
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def get_session_detail(self, session_id: str, user_id: str) -> ChatSessionDetail:
        """Get a session and all of its messages ordered chronologically."""
        session = self.get_session(session_id=session_id, user_id=user_id)

        if self._supabase_client is not None:
            res = (
                self._supabase_client.table("messages")
                .select("*")
                .eq("session_id", session_id)
                .order("created_at", desc=False)
                .execute()
            )
            messages = [self._row_to_message(r) for r in (res.data or [])]
            return ChatSessionDetail(session=session, messages=messages)

        messages = [
            m for m in self._local_messages.values() if m.session_id == session_id
        ]
        messages.sort(key=lambda m: m.created_at)
        return ChatSessionDetail(session=session, messages=messages)

    def delete_session(self, session_id: str, user_id: str) -> ChatSessionSummary:
        """Delete a user's chat session and cascade delete its messages."""
        session = self.get_session(session_id=session_id, user_id=user_id)

        if self._supabase_client is not None:
            self._supabase_client.table("chat_sessions").delete().eq("id", session_id).execute()
            return session

        self._local_sessions.pop(session_id, None)
        msg_ids = [
            mid for mid, msg in self._local_messages.items() if msg.session_id == session_id
        ]
        for mid in msg_ids:
            self._local_messages.pop(mid, None)
        return session

    def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        detected_language: DetectedLanguage = "en",
        citations: list[Citation] | None = None,
        latency_ms: int | None = None,
        message_id: str | None = None,
    ) -> ChatMessage:
        """Append a message to a chat session and bump session `updated_at`."""
        mid = message_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        citation_list = citations or []

        msg = ChatMessage(
            id=mid,
            session_id=session_id,
            role=role,
            content=content,
            detected_language=detected_language,
            citations=citation_list,
            feedback_rating=None,
            feedback_comment=None,
            latency_ms=latency_ms,
            created_at=now,
        )

        if self._supabase_client is not None:
            payload = {
                "id": msg.id,
                "session_id": msg.session_id,
                "role": msg.role,
                "content": msg.content,
                "detected_language": msg.detected_language,
                "citations": [c.model_dump() for c in citation_list],
                "latency_ms": msg.latency_ms,
                "created_at": now.isoformat(),
            }
            res = self._supabase_client.table("messages").insert(payload).execute()
            self._supabase_client.table("chat_sessions").update(
                {"updated_at": now.isoformat()}
            ).eq("id", session_id).execute()
            rows = res.data or [payload]
            return self._row_to_message(rows[0])

        self._local_messages[mid] = msg
        if session_id in self._local_sessions:
            self._local_sessions[session_id] = self._local_sessions[session_id].model_copy(
                update={"updated_at": now}
            )
        return msg

    def update_message_feedback(
        self,
        message_id: str,
        user_id: str,
        rating: Literal[-1, 1],
        comment: str | None = None,
    ) -> ChatMessage:
        """Record student thumbs-up / thumbs-down feedback on an assistant message."""
        if self._supabase_client is not None:
            res = (
                self._supabase_client.table("messages")
                .select("*")
                .eq("id", message_id)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            if not rows:
                raise ResourceNotFoundError("Message", message_id)
            msg = self._row_to_message(rows[0])
            # Verify ownership of parent session
            self.get_session(session_id=msg.session_id, user_id=user_id)

            updated_res = (
                self._supabase_client.table("messages")
                .update({"feedback_rating": rating, "feedback_comment": comment})
                .eq("id", message_id)
                .execute()
            )
            updated_rows = updated_res.data or []
            if updated_rows:
                return self._row_to_message(updated_rows[0])

        if message_id not in self._local_messages:
            raise ResourceNotFoundError("Message", message_id)
        msg = self._local_messages[message_id]
        self.get_session(session_id=msg.session_id, user_id=user_id)

        updated = msg.model_copy(
            update={"feedback_rating": rating, "feedback_comment": comment}
        )
        self._local_messages[message_id] = updated
        return updated

    @staticmethod
    def _row_to_session(row: dict[str, Any]) -> ChatSessionSummary:
        return ChatSessionSummary(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            title=row.get("title", "New Conversation"),
            language=row.get("language", "en"),
            category_filter=row.get("category_filter", "all"),
            is_archived=bool(row.get("is_archived", False)),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_message(row: dict[str, Any]) -> ChatMessage:
        raw_citations = row.get("citations") or []
        citations = [
            Citation(**c) if isinstance(c, dict) else c for c in raw_citations
        ]
        return ChatMessage(
            id=str(row["id"]),
            session_id=str(row["session_id"]),
            role=row["role"],
            content=row["content"],
            detected_language=row.get("detected_language", "en"),
            citations=citations,
            feedback_rating=row.get("feedback_rating"),
            feedback_comment=row.get("feedback_comment"),
            latency_ms=row.get("latency_ms"),
            created_at=row["created_at"],
        )


_chat_repo_instance: ChatRepository | None = None


def get_chat_repository() -> ChatRepository:
    """FastAPI dependency returning singleton ChatRepository."""
    global _chat_repo_instance
    if _chat_repo_instance is None:
        _chat_repo_instance = ChatRepository()
    return _chat_repo_instance

