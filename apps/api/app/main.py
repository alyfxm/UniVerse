"""FastAPI application entry point and middleware configuration."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, request_id_ctx
from app.routers import (
    auth,
    chat,
    documents,
    enterprise,
    eval as eval_router,
    health,
    search,
)


class CorrelationIdMiddleware:
    """Pure ASGI middleware that attaches and propagates X-Request-ID."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        raw_req_id = headers.get(b"x-request-id")
        req_id = (
            raw_req_id.decode("latin1")
            if raw_req_id
            else f"req_{uuid.uuid4().hex[:12]}"
        )
        token = request_id_ctx.set(req_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers") or [])
                raw_headers.append((b"x-request-id", req_id.encode("latin1")))
                message["headers"] = raw_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_ctx.reset(token)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    settings.ensure_directories()
    yield


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application instance."""
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="UniVerse Multilingual AI Campus Assistant API (Bahasa Melayu & English)",
        lifespan=lifespan,
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # Request Correlation ID Middleware (Pure ASGI)
    app.add_middleware(CorrelationIdMiddleware)

    # Standardized Exception Handlers
    register_exception_handlers(app)

    # API v1 Routers
    app.include_router(health.router, prefix=settings.API_V1_PREFIX)
    app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
    app.include_router(documents.admin_router, prefix=settings.API_V1_PREFIX)
    app.include_router(documents.public_doc_router, prefix=settings.API_V1_PREFIX)
    app.include_router(chat.router, prefix=settings.API_V1_PREFIX)
    app.include_router(search.router, prefix=settings.API_V1_PREFIX)
    app.include_router(eval_router.router, prefix=settings.API_V1_PREFIX)
    app.include_router(enterprise.integrations_router, prefix=settings.API_V1_PREFIX)
    app.include_router(enterprise.student_router, prefix=settings.API_V1_PREFIX)
    app.include_router(enterprise.analytics_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()

