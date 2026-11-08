"""Enterprise Services for UniVerse 2.0:
- Phase 3: Omnichannel Bot Gateway (WhatsApp & Telegram formatting + session mapping)
- Phase 4: Student Information System (SIS) Personalization & Agentic Workflows
  (Advisor Booking, Auto-Filled Deferment PDF Form Generation, .ics Academic Calendar Export)
- Phase 5: Institutional Analytics & Knowledge Gap Detection Engine
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import uuid

from fastapi import Depends
import pymupdf as fitz

from app.models.auth import UserProfile
from app.models.enterprise import (
    AdvisorAppointment,
    AdvisorAppointmentRequest,
    CategoryInquiryCount,
    DefermentFormPrefillRequest,
    InstitutionalAnalyticsSummary,
    KnowledgeGapItem,
    OmnichannelMessageRequest,
    OmnichannelMessageResponse,
    StudentSisProfile,
)
from app.repositories.chat_repo import ChatRepository, get_chat_repository
from app.services.rag_service import RagService, get_rag_service


class EnterpriseCampusService:
    """Provides SIS personalization, agentic tools, omnichannel gateway, and campus analytics."""

    def __init__(
        self,
        rag_service: RagService,
        chat_repo: ChatRepository,
    ) -> None:
        self.rag_service = rag_service
        self.chat_repo = chat_repo
        self._appointments: list[AdvisorAppointment] = []
        self._external_session_map: dict[str, str] = {}

    # =========================================================================
    # Phase 4: SIS Profile & Agentic Workflows
    # =========================================================================

    @staticmethod
    def get_sis_profile(user: UserProfile) -> StudentSisProfile:
        """Return anonymized/structured SIS academic profile for the authenticated student."""
        return StudentSisProfile(
            user_id=user.id,
            matric_number="U20251048",
            full_name=user.display_name,
            faculty="Faculty of Computer Science & Information Technology",
            program="Bachelor of Computer Science (Artificial Intelligence)",
            study_year=2,
            semester=1,
            cgpa=3.74,
            completed_courses=[
                "CSC1101 (Programming Fundamentals)",
                "CSC1102 (Data Structures & Algorithms)",
                "MAT1101 (Discrete Mathematics)",
                "CSC2104 (Database Systems)",
            ],
            eligible_electives=[
                "CSC3201 (Machine Learning - Prerequisite CSC1102 Met)",
                "CSC3205 (Natural Language Processing - Prerequisite CSC1102 Met)",
            ],
            academic_advisor="Assoc. Prof. Dr. Razak Bin Mahmud",
            advisor_email="razak.mahmud@universe.edu.my",
            scholarship_status="Active — Dean's List Merit Scholarship",
        )

    def book_advisor_appointment(
        self,
        user: UserProfile,
        req: AdvisorAppointmentRequest,
    ) -> AdvisorAppointment:
        """Agentic workflow: book a consultation slot with the student's assigned Academic Advisor."""
        sis = self.get_sis_profile(user)
        appointment = AdvisorAppointment(
            appointment_id=f"apt_{uuid.uuid4().hex[:10]}",
            student_id=user.id,
            matric_number=sis.matric_number,
            advisor_name=sis.academic_advisor,
            advisor_email=sis.advisor_email,
            topic=req.topic.strip(),
            preferred_slot=req.preferred_slot.strip(),
            status="confirmed",
            created_at=datetime.now(timezone.utc),
        )
        self._appointments.append(appointment)
        return appointment

    def list_user_appointments(self, user_id: str) -> list[AdvisorAppointment]:
        """List advisor appointments booked by `user_id`."""
        return [a for a in self._appointments if a.student_id == user_id]

    def generate_prefilled_deferment_pdf(
        self,
        user: UserProfile,
        req: DefermentFormPrefillRequest,
    ) -> bytes:
        """Agentic workflow: generate an official University Deferment Application PDF pre-filled with SIS details."""
        sis = self.get_sis_profile(user)
        doc = fitz.open()
        page = doc.new_page()
        rect = fitz.Rect(54, 54, 540, 760)

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        form_content = (
            "UNIVERSE UNIVERSITY — OFFICIAL ACADEMIC DEFERMENT FORM (BORANG PENANGGUHAN PENGAJIAN)\n"
            "=====================================================================================\n\n"
            f"Generated Reference ID : DEF-{uuid.uuid4().hex[:8].upper()}\n"
            f"Timestamp              : {now_str}\n\n"
            "1. STUDENT INFORMATION (MAKLUMAT PELAJAR - AUTO-FILLED FROM SIS)\n"
            f"   Full Name           : {sis.full_name}\n"
            f"   Matric Number       : {sis.matric_number}\n"
            f"   Email               : {user.email}\n"
            f"   Faculty             : {sis.faculty}\n"
            f"   Program             : {sis.program}\n"
            f"   Current Standing    : Year {sis.study_year}, Semester {sis.semester} (CGPA: {sis.cgpa})\n"
            f"   Academic Advisor    : {sis.academic_advisor}\n\n"
            "2. DEFERMENT REQUEST DETAILS (BUTIRAN PERMOHONAN PENANGGUHAN)\n"
            f"   Reason Category     : {req.reason_category.upper()}\n"
            f"   Supporting Details  : {req.supporting_details}\n\n"
            "3. POLICY COMPLIANCE CHECK (SEMAKAN PERATURAN AKADEMIK)\n"
            "   - Must be submitted by Week 4 of the semester (Undergraduate Academic Regulations Page 2).\n"
            "   - Medical deferment requires an official Government Hospital or Panel Clinic certificate.\n"
        )
        page.insert_textbox(rect, form_content, fontsize=10)
        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes

    @staticmethod
    def generate_academic_deadlines_ics() -> str:
        """Agentic workflow: export verified campus deadlines as an iCalendar (.ics) file."""
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//UniVerse AI Campus Assistant//Academic Calendar 2026//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VEVENT",
            "UID:universe-add-drop-deadline-2026@universe.edu.my",
            "DTSTAMP:20261101T080000Z",
            "DTSTART:20261115T090000Z",
            "DTEND:20261115T170000Z",
            "SUMMARY:UniVerse: Course Add/Drop Window Deadline (Week 2)",
            "DESCRIPTION:Final day to add or drop courses (Undergraduate Academic Regulations Page 1).",
            "END:VEVENT",
            "BEGIN:VEVENT",
            "UID:universe-deferment-deadline-2026@universe.edu.my",
            "DTSTAMP:20261101T080000Z",
            "DTSTART:20261129T090000Z",
            "DTEND:20261129T170000Z",
            "SUMMARY:UniVerse: Deferment of Study Application Deadline (Week 4)",
            "DESCRIPTION:Official deadline for semester deferment applications (Academic Regulations Page 2).",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
        return "\r\n".join(lines) + "\r\n"

    # =========================================================================
    # Phase 3: Omnichannel Webhook Gateway (WhatsApp & Telegram)
    # =========================================================================

    def handle_omnichannel_webhook(
        self,
        payload: OmnichannelMessageRequest,
    ) -> OmnichannelMessageResponse:
        """Process a student message from WhatsApp or Telegram and return mobile-formatted answer + citations."""
        channel_key = f"{payload.channel}:{payload.external_user_id}"
        existing_session_id = self._external_session_map.get(channel_key)

        synthetic_user_id = str(
            uuid.uuid5(uuid.NAMESPACE_DNS, f"universe.{channel_key}")
        )
        rag_res = self.rag_service.answer_query(
            user_id=synthetic_user_id,
            query=payload.text,
            session_id=existing_session_id,
            language_pref="auto",
            category_filter="all",
        )
        self._external_session_map[channel_key] = rag_res.session_id

        # Append compact mobile source references for WhatsApp/Telegram
        if rag_res.citations:
            ref_header = (
                "\n\n📚 *Rujukan Rasmi:*"
                if rag_res.detected_language == "ms"
                else "\n\n📚 *Verified Sources:*"
            )
            ref_lines = [
                f"[{c.citation_index}] {c.document_title} (p.{c.page_number})"
                for c in rag_res.citations
            ]
            formatted_reply = f"{rag_res.answer}{ref_header}\n" + "\n".join(ref_lines)
        else:
            formatted_reply = rag_res.answer

        return OmnichannelMessageResponse(
            channel=payload.channel,
            external_user_id=payload.external_user_id,
            session_id=rag_res.session_id,
            detected_language=rag_res.detected_language,
            reply_text=formatted_reply,
            citations=rag_res.citations,
            is_grounded=rag_res.is_grounded,
        )

    # =========================================================================
    # Phase 5: Institutional Analytics & Knowledge Gap Detection
    # =========================================================================

    def compute_institutional_analytics(self) -> InstitutionalAnalyticsSummary:
        """Analyze campus chat sessions and messages to detect knowledge gaps and ticket deflection ROI."""
        all_sessions = list(self.chat_repo._local_sessions.values())
        all_messages = list(self.chat_repo._local_messages.values())

        user_messages = [m for m in all_messages if m.role == "user"]
        assistant_messages = [m for m in all_messages if m.role == "assistant"]

        grounded_count = sum(1 for m in assistant_messages if len(m.citations) > 0)
        unanswered_count = max(0, len(assistant_messages) - grounded_count)
        total_queries = len(user_messages)

        grounding_rate = (
            round(grounded_count / len(assistant_messages), 4)
            if assistant_messages
            else 1.0
        )

        # Language distribution
        lang_counter: Counter[str] = Counter(
            m.detected_language for m in user_messages
        )
        language_distribution = {
            "en": lang_counter.get("en", 0),
            "ms": lang_counter.get("ms", 0),
        }

        # Category breakdown from sessions
        cat_counter: Counter[str] = Counter(
            s.category_filter for s in all_sessions
        )
        category_breakdown = [
            CategoryInquiryCount(category=cat, count=cnt)
            for cat, cnt in cat_counter.most_common()
        ]

        # Identify knowledge gaps: pair each user message with its subsequent assistant message in the same session
        session_msgs_map: dict[str, list] = {}
        for m in all_messages:
            session_msgs_map.setdefault(m.session_id, []).append(m)

        gap_map: dict[str, KnowledgeGapItem] = {}
        for sid, msgs in session_msgs_map.items():
            msgs_sorted = sorted(msgs, key=lambda x: x.created_at)
            sess_obj = self.chat_repo._local_sessions.get(sid)
            cat_filter = sess_obj.category_filter if sess_obj else "all"

            for idx, msg in enumerate(msgs_sorted):
                if msg.role == "user" and idx + 1 < len(msgs_sorted):
                    reply = msgs_sorted[idx + 1]
                    if reply.role == "assistant" and len(reply.citations) == 0:
                        norm_q = msg.content.strip()
                        key = norm_q.lower()
                        if key in gap_map:
                            existing = gap_map[key]
                            gap_map[key] = existing.model_copy(
                                update={
                                    "occurrences": existing.occurrences + 1,
                                    "last_asked_at": msg.created_at,
                                }
                            )
                        else:
                            gap_map[key] = KnowledgeGapItem(
                                query=norm_q,
                                language=msg.detected_language,
                                category_filter=cat_filter,
                                occurrences=1,
                                last_asked_at=msg.created_at,
                            )

        knowledge_gaps = sorted(
            gap_map.values(),
            key=lambda g: (g.occurrences, g.last_asked_at),
            reverse=True,
        )

        # Each grounded answer deflects ~1 front-desk ticket (~12 minutes / 0.2 hours of staff time)
        estimated_hours_saved = round(grounded_count * 0.2, 2)

        return InstitutionalAnalyticsSummary(
            total_sessions=len(all_sessions),
            total_student_queries=total_queries,
            grounded_answers_count=grounded_count,
            unanswered_queries_count=unanswered_count,
            grounding_rate=grounding_rate,
            estimated_tickets_deflected=grounded_count,
            estimated_hours_saved=estimated_hours_saved,
            language_distribution=language_distribution,
            category_breakdown=category_breakdown,
            knowledge_gaps=knowledge_gaps,
        )


_enterprise_service_instance: EnterpriseCampusService | None = None


def get_enterprise_service(
    rag_service: RagService = Depends(get_rag_service),
    chat_repo: ChatRepository = Depends(get_chat_repository),
) -> EnterpriseCampusService:
    """FastAPI dependency returning singleton EnterpriseCampusService."""
    global _enterprise_service_instance
    if (
        _enterprise_service_instance is None
        or _enterprise_service_instance.rag_service is not rag_service
        or _enterprise_service_instance.chat_repo is not chat_repo
    ):
        _enterprise_service_instance = EnterpriseCampusService(
            rag_service=rag_service,
            chat_repo=chat_repo,
        )
    return _enterprise_service_instance

