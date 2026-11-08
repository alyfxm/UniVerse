"""Enterprise Routers for UniVerse 2.0:
- `/api/v1/integrations/*`: Omnichannel WhatsApp & Telegram Webhook Gateway
- `/api/v1/student/*`: SIS Profile Personalization & Agentic Workflows (Advisor Booking, Deferment Form PDF, .ics Calendar)
- `/api/v1/admin/analytics/*`: Institutional Analytics & Knowledge Gap Detection
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.core.security import get_current_user, require_admin
from app.models.auth import UserProfile
from app.models.enterprise import (
    AdvisorAppointment,
    AdvisorAppointmentRequest,
    DefermentFormPrefillRequest,
    InstitutionalAnalyticsSummary,
    OmnichannelMessageRequest,
    OmnichannelMessageResponse,
    StudentSisProfile,
)
from app.services.enterprise_service import (
    EnterpriseCampusService,
    get_enterprise_service,
)

integrations_router = APIRouter(prefix="/integrations", tags=["Omnichannel Gateway"])
student_router = APIRouter(prefix="/student", tags=["Student SIS & Agentic Tools"])
analytics_router = APIRouter(prefix="/admin/analytics", tags=["Admin Analytics"])


# =============================================================================
# Phase 3: Omnichannel Webhook Gateway (WhatsApp & Telegram)
# =============================================================================

@integrations_router.post(
    "/omnichannel/webhook",
    response_model=OmnichannelMessageResponse,
)
async def handle_omnichannel_message(
    payload: OmnichannelMessageRequest,
    enterprise_service: EnterpriseCampusService = Depends(get_enterprise_service),
) -> OmnichannelMessageResponse:
    """Receive an incoming WhatsApp or Telegram message and return a cited RAG reply."""
    return enterprise_service.handle_omnichannel_webhook(payload)


# =============================================================================
# Phase 4: Student SIS Context & Agentic Workflows
# =============================================================================

@student_router.get("/sis-profile", response_model=StudentSisProfile)
async def get_student_sis_profile(
    current_user: UserProfile = Depends(get_current_user),
    enterprise_service: EnterpriseCampusService = Depends(get_enterprise_service),
) -> StudentSisProfile:
    """Return the authenticated student's SIS academic record and prerequisite eligibility."""
    return enterprise_service.get_sis_profile(current_user)


@student_router.post(
    "/agent/book-advisor",
    response_model=AdvisorAppointment,
    status_code=status.HTTP_201_CREATED,
)
async def book_academic_advisor_slot(
    payload: AdvisorAppointmentRequest,
    current_user: UserProfile = Depends(get_current_user),
    enterprise_service: EnterpriseCampusService = Depends(get_enterprise_service),
) -> AdvisorAppointment:
    """Agentic workflow: book a consultation slot with the student's assigned Academic Advisor."""
    return enterprise_service.book_advisor_appointment(current_user, payload)


@student_router.get(
    "/agent/appointments",
    response_model=list[AdvisorAppointment],
)
async def list_my_advisor_appointments(
    current_user: UserProfile = Depends(get_current_user),
    enterprise_service: EnterpriseCampusService = Depends(get_enterprise_service),
) -> list[AdvisorAppointment]:
    """List the authenticated student's booked academic advisor appointments."""
    return enterprise_service.list_user_appointments(current_user.id)


@student_router.post("/agent/deferment-form/pdf")
async def generate_prefilled_deferment_form(
    payload: DefermentFormPrefillRequest,
    current_user: UserProfile = Depends(get_current_user),
    enterprise_service: EnterpriseCampusService = Depends(get_enterprise_service),
) -> Response:
    """Agentic workflow: generate and download an official Deferment of Study PDF pre-filled with SIS data."""
    pdf_bytes = enterprise_service.generate_prefilled_deferment_pdf(
        current_user, payload
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="UniVerse_Prefilled_Deferment_Form.pdf"',
        },
    )


@student_router.get("/agent/deadlines.ics")
async def export_academic_deadlines_calendar(
    _current_user: UserProfile = Depends(get_current_user),
    enterprise_service: EnterpriseCampusService = Depends(get_enterprise_service),
) -> Response:
    """Agentic workflow: export verified semester deadlines as an iCalendar (.ics) file."""
    ics_text = enterprise_service.generate_academic_deadlines_ics()
    return Response(
        content=ics_text,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="universe_academic_deadlines_2026.ics"',
        },
    )


# =============================================================================
# Phase 5: Institutional Analytics & Knowledge Gap Detection
# =============================================================================

@analytics_router.get("/summary", response_model=InstitutionalAnalyticsSummary)
async def get_institutional_analytics(
    _admin_user: UserProfile = Depends(require_admin),
    enterprise_service: EnterpriseCampusService = Depends(get_enterprise_service),
) -> InstitutionalAnalyticsSummary:
    """Return institutional inquiry analytics, ticket deflection ROI, and unanswered knowledge gaps."""
    return enterprise_service.compute_institutional_analytics()

