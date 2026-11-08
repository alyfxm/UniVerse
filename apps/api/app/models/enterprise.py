"""Pydantic models for Enterprise Phases 3, 4, and 5:
- Phase 3: Omnichannel Webhook Gateway (Telegram & WhatsApp)
- Phase 4: Student Information System (SIS) Personalization & Agentic Workflows
- Phase 5: Institutional Analytics & Knowledge Gap Detection
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

from app.models.chat import Citation


# =============================================================================
# Phase 3: Omnichannel Messaging (WhatsApp & Telegram)
# =============================================================================

class OmnichannelMessageRequest(BaseModel):
    """Incoming webhook payload from Telegram or WhatsApp student bot."""

    channel: Literal["telegram", "whatsapp"]
    external_user_id: str = Field(..., min_length=2, max_length=120)
    student_name: str = Field(default="Campus Student")
    text: str = Field(..., min_length=1, max_length=2000)


class OmnichannelMessageResponse(BaseModel):
    """Formatted bot reply with mobile-friendly citations."""

    channel: Literal["telegram", "whatsapp"]
    external_user_id: str
    session_id: str
    detected_language: Literal["en", "ms"]
    reply_text: str
    citations: list[Citation] = Field(default_factory=list)
    is_grounded: bool = True


# =============================================================================
# Phase 4: SIS Personalization & Agentic Workflows
# =============================================================================

class StudentSisProfile(BaseModel):
    """Academic record from the Student Information System (SIS)."""

    user_id: str
    matric_number: str
    full_name: str
    faculty: str
    program: str
    study_year: int = Field(..., ge=1, le=6)
    semester: int = Field(..., ge=1, le=3)
    cgpa: float = Field(..., ge=0.0, le=4.0)
    completed_courses: list[str]
    eligible_electives: list[str]
    academic_advisor: str
    advisor_email: str
    scholarship_status: str


class AdvisorAppointmentRequest(BaseModel):
    """Agentic workflow request to book an academic advisor consultation."""

    topic: str = Field(..., min_length=3, max_length=300)
    preferred_slot: str = Field(
        default="Thursday, 14:00 - 14:30 MYT",
        min_length=3,
        max_length=120,
    )


class AdvisorAppointment(BaseModel):
    """Confirmed academic advisor appointment."""

    appointment_id: str
    student_id: str
    matric_number: str
    advisor_name: str
    advisor_email: str
    topic: str
    preferred_slot: str
    location: str = "Faculty of Computer Science & IT, Level 3, Room C-312"
    status: Literal["confirmed", "cancelled"] = "confirmed"
    created_at: datetime


class DefermentFormPrefillRequest(BaseModel):
    """Agentic workflow request to auto-fill an official Deferment of Study PDF form."""

    reason_category: Literal["medical", "financial", "personal"] = "medical"
    supporting_details: str = Field(
        default="Official Hospital Medical Certificate attached for Semester 1.",
        min_length=3,
        max_length=500,
    )


# =============================================================================
# Phase 5: Institutional Analytics & Knowledge Gap Detection
# =============================================================================

class KnowledgeGapItem(BaseModel):
    """Represents an unanswerable or low-confidence student query requiring admin documentation."""

    query: str
    language: Literal["en", "ms"]
    category_filter: str
    occurrences: int = 1
    last_asked_at: datetime


class CategoryInquiryCount(BaseModel):
    category: str
    count: int


class InstitutionalAnalyticsSummary(BaseModel):
    """Executive campus metrics for the Admin Dashboard."""

    total_sessions: int
    total_student_queries: int
    grounded_answers_count: int
    unanswered_queries_count: int
    grounding_rate: float = Field(..., ge=0.0, le=1.0)
    estimated_tickets_deflected: int
    estimated_hours_saved: float
    language_distribution: dict[str, int]
    category_breakdown: list[CategoryInquiryCount]
    knowledge_gaps: list[KnowledgeGapItem]

