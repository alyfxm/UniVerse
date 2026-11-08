/**
 * Shared TypeScript contracts matching the FastAPI `/api/v1` Pydantic models.
 */

export type UserRole = "student" | "admin";
export type SupportedLanguage = "en" | "ms";
export type QueryLanguagePreference = "auto" | "en" | "ms";
export type DocumentCategory =
  | "academic"
  | "facilities"
  | "events"
  | "financial"
  | "general";
export type CategoryFilter = DocumentCategory | "all";
export type DocumentLanguage = "en" | "ms" | "bilingual";
export type DocumentStatus = "queued" | "processing" | "indexed" | "failed";

export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  role: UserRole;
  preferred_language: SupportedLanguage;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  citation_index: number;
  document_id: string;
  document_title: string;
  category: string;
  page_number: number;
  snippet: string;
  relevance_score: number;
  file_url: string;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  detected_language: SupportedLanguage;
  citations: Citation[];
  feedback_rating?: -1 | 1 | null;
  feedback_comment?: string | null;
  latency_ms?: number | null;
  created_at: string;
}

export interface ChatSessionSummary {
  id: string;
  user_id: string;
  title: string;
  language: SupportedLanguage;
  category_filter: CategoryFilter;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface ChatSessionDetail {
  session: ChatSessionSummary;
  messages: ChatMessage[];
}

export interface ChatQueryResponse {
  message_id: string;
  session_id: string;
  answer: string;
  detected_language: SupportedLanguage;
  citations: Citation[];
  is_grounded: boolean;
  latency_ms: number;
}

export interface DocumentMetadata {
  id: string;
  title: string;
  filename: string;
  file_hash: string;
  storage_path: string;
  category: DocumentCategory;
  language: DocumentLanguage;
  status: DocumentStatus;
  error_message?: string | null;
  page_count: number;
  chunk_count: number;
  file_size_bytes: number;
  uploaded_by?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface EvalCaseResult {
  case_id: string;
  language: SupportedLanguage;
  category: DocumentCategory;
  question: string;
  expected_page: number;
  retrieved_pages: number[];
  answer: string;
  faithfulness: number;
  answer_relevance: number;
  context_recall: number;
  citation_accuracy: number;
  passed: boolean;
}

export interface EvalRunSummary {
  id: string;
  triggered_by?: string | null;
  total_questions: number;
  avg_faithfulness: number;
  avg_answer_relevance: number;
  avg_context_recall: number;
  avg_citation_accuracy: number;
  case_results: EvalCaseResult[];
  created_at: string;
}

export interface HighlightRect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface PagePreviewResponse {
  document_id: string;
  document_title: string;
  page_number: number;
  total_pages: number;
  page_text: string;
  image_data_url: string;
  highlight_boxes: HighlightRect[];
}

export interface StudentSisProfile {
  user_id: string;
  matric_number: string;
  full_name: string;
  faculty: string;
  program: string;
  study_year: number;
  semester: number;
  cgpa: number;
  completed_courses: string[];
  eligible_electives: string[];
  academic_advisor: string;
  advisor_email: string;
  scholarship_status: string;
}

export interface AdvisorAppointment {
  appointment_id: string;
  student_id: string;
  matric_number: string;
  advisor_name: string;
  advisor_email: string;
  topic: string;
  preferred_slot: string;
  location: string;
  status: "confirmed" | "cancelled";
  created_at: string;
}

export interface KnowledgeGapItem {
  query: string;
  language: SupportedLanguage;
  category_filter: string;
  occurrences: number;
  last_asked_at: string;
}

export interface InstitutionalAnalyticsSummary {
  total_sessions: number;
  total_student_queries: number;
  grounded_answers_count: number;
  unanswered_queries_count: number;
  grounding_rate: number;
  estimated_tickets_deflected: number;
  estimated_hours_saved: number;
  language_distribution: Record<string, number>;
  category_breakdown: { category: string; count: number }[];
  knowledge_gaps: KnowledgeGapItem[];
}

