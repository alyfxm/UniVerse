/**
 * Typed API Client for communicating with the FastAPI `/api/v1` backend.
 */

import {
  AdvisorAppointment,
  CategoryFilter,
  ChatMessage,
  ChatQueryResponse,
  ChatSessionDetail,
  ChatSessionSummary,
  DocumentCategory,
  DocumentLanguage,
  DocumentMetadata,
  EvalRunSummary,
  InstitutionalAnalyticsSummary,
  PagePreviewResponse,
  QueryLanguagePreference,
  StudentSisProfile,
  SupportedLanguage,
  UserProfile,
  UserRole,
} from "@/types/api";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export const BACKEND_ORIGIN = API_BASE_URL.replace(/\/api\/v1\/?$/, "");

async function requestJson<T>(
  path: string,
  token: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${token}`);
  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorMessage = `Request failed with status ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson?.error?.message) {
        errorMessage = errJson.error.message;
      }
    } catch {
      // Fallback to status message
    }
    throw new Error(errorMessage);
  }

  return response.json() as Promise<T>;
}

export async function fetchDemoToken(
  role: UserRole = "student",
  preferredLanguage: SupportedLanguage = "en"
): Promise<{ access_token: string; user: UserProfile }> {
  const response = await fetch(`${API_BASE_URL}/auth/demo-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      role,
      preferred_language: preferredLanguage,
    }),
  });
  if (!response.ok) {
    throw new Error("Failed to acquire demo session token");
  }
  return response.json();
}

export async function fetchMyProfile(token: string): Promise<UserProfile> {
  return requestJson<UserProfile>("/auth/me", token);
}

export async function updateMyProfile(
  token: string,
  payload: { display_name?: string; preferred_language?: SupportedLanguage }
): Promise<UserProfile> {
  return requestJson<UserProfile>("/auth/me", token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function fetchChatSessions(
  token: string
): Promise<ChatSessionSummary[]> {
  const res = await requestJson<{ sessions: ChatSessionSummary[]; total: number }>(
    "/chat/sessions",
    token
  );
  return res.sessions;
}

export async function fetchChatSessionDetail(
  token: string,
  sessionId: string
): Promise<ChatSessionDetail> {
  return requestJson<ChatSessionDetail>(`/chat/sessions/${sessionId}`, token);
}

export async function deleteChatSession(
  token: string,
  sessionId: string
): Promise<ChatSessionSummary> {
  return requestJson<ChatSessionSummary>(`/chat/sessions/${sessionId}`, token, {
    method: "DELETE",
  });
}

export async function submitMessageFeedback(
  token: string,
  messageId: string,
  rating: -1 | 1,
  comment?: string
): Promise<ChatMessage> {
  return requestJson<ChatMessage>(
    `/chat/messages/${messageId}/feedback`,
    token,
    {
      method: "POST",
      body: JSON.stringify({ rating, comment }),
    }
  );
}

export async function streamChatQuery(
  token: string,
  params: {
    session_id?: string | null;
    query: string;
    language?: QueryLanguagePreference;
    category_filter?: CategoryFilter;
  },
  onDelta: (deltaText: string) => void
): Promise<ChatQueryResponse> {
  const response = await fetch(`${API_BASE_URL}/chat/query`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session_id: params.session_id || null,
      query: params.query,
      language: params.language || "auto",
      category_filter: params.category_filter || "all",
      stream: true,
    }),
  });

  if (!response.ok || !response.body) {
    throw new Error(`Chat query failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResponse: ChatQueryResponse | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n\n");
    buffer = lines.pop() || "";

    for (const block of lines) {
      const trimmed = block.trim();
      if (!trimmed.startsWith("data: ")) continue;
      const jsonStr = trimmed.slice(6);
      try {
        const parsed = JSON.parse(jsonStr);
        if (parsed.type === "delta" && typeof parsed.content === "string") {
          onDelta(parsed.content);
        } else if (parsed.type === "done") {
          finalResponse = parsed as ChatQueryResponse;
        }
      } catch {
        // Ignore malformed SSE frame
      }
    }
  }

  if (!finalResponse) {
    throw new Error("Stream ended without final response payload");
  }
  return finalResponse;
}

export async function fetchAdminDocuments(
  token: string,
  category?: string
): Promise<DocumentMetadata[]> {
  const query = category && category !== "all" ? `?category=${category}` : "";
  const res = await requestJson<{ documents: DocumentMetadata[]; total: number }>(
    `/admin/documents${query}`,
    token
  );
  return res.documents;
}

export async function uploadAdminDocument(
  token: string,
  params: {
    file: File;
    title: string;
    category: DocumentCategory;
    language: DocumentLanguage;
  }
): Promise<DocumentMetadata> {
  const formData = new FormData();
  formData.append("file", params.file);
  formData.append("title", params.title);
  formData.append("category", params.category);
  formData.append("language", params.language);

  return requestJson<DocumentMetadata>("/admin/documents", token, {
    method: "POST",
    body: formData,
  });
}

export async function updateAdminDocument(
  token: string,
  docId: string,
  payload: {
    title?: string;
    category?: DocumentCategory;
    language?: DocumentLanguage;
    is_active?: boolean;
  }
): Promise<DocumentMetadata> {
  return requestJson<DocumentMetadata>(`/admin/documents/${docId}`, token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteAdminDocument(
  token: string,
  docId: string
): Promise<DocumentMetadata> {
  return requestJson<DocumentMetadata>(`/admin/documents/${docId}`, token, {
    method: "DELETE",
  });
}

export async function runRagEvaluation(token: string): Promise<EvalRunSummary> {
  return requestJson<EvalRunSummary>("/admin/eval/run", token, {
    method: "POST",
  });
}

export async function fetchRagEvaluationRuns(
  token: string
): Promise<EvalRunSummary[]> {
  const res = await requestJson<{ runs: EvalRunSummary[]; total: number }>(
    "/admin/eval/runs",
    token
  );
  return res.runs;
}

export async function fetchPageHighlightPreview(
  token: string,
  documentId: string,
  pageNumber: number,
  snippet?: string
): Promise<PagePreviewResponse> {
  const qs = snippet ? `?highlight=${encodeURIComponent(snippet)}` : "";
  return requestJson<PagePreviewResponse>(
    `/documents/${documentId}/pages/${pageNumber}/preview${qs}`,
    token
  );
}

export async function fetchStudentSisProfile(
  token: string
): Promise<StudentSisProfile> {
  return requestJson<StudentSisProfile>("/student/sis-profile", token);
}

export async function bookAcademicAdvisor(
  token: string,
  payload: { topic: string; preferred_slot: string }
): Promise<AdvisorAppointment> {
  return requestJson<AdvisorAppointment>("/student/agent/book-advisor", token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchInstitutionalAnalytics(
  token: string
): Promise<InstitutionalAnalyticsSummary> {
  return requestJson<InstitutionalAnalyticsSummary>(
    "/admin/analytics/summary",
    token
  );
}

