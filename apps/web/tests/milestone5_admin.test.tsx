import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AdminDashboard } from "@/components/AdminDashboard";
import { LanguageProvider } from "@/context/LanguageContext";

const mockLoginWithDemoRole = vi.fn();
let mockCurrentUserRole: "student" | "admin" = "admin";

vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: "99999999-9999-9999-9999-999999999999",
      email: "admin@universe.edu.my",
      display_name: "Dr. Farah",
      role: mockCurrentUserRole,
      preferred_language: "en",
      created_at: "2026-11-08T00:00:00Z",
      updated_at: "2026-11-08T00:00:00Z",
    },
    token: "mock-admin-jwt",
    isLoading: false,
    error: null,
    loginWithDemoRole: mockLoginWithDemoRole,
    logout: vi.fn(),
  }),
}));

vi.mock("@/lib/api", () => ({
  fetchAdminDocuments: vi.fn().mockResolvedValue([
    {
      id: "doc_1",
      title: "Undergraduate Academic Regulations 2026",
      filename: "Academic_Regulations_2026.pdf",
      file_hash: "abc1234",
      storage_path: "doc_1/Academic_Regulations_2026.pdf",
      category: "academic",
      language: "bilingual",
      status: "indexed",
      page_count: 2,
      chunk_count: 4,
      file_size_bytes: 24500,
      is_active: true,
      created_at: "2026-11-08T00:00:00Z",
      updated_at: "2026-11-08T00:00:00Z",
    },
  ]),
  fetchRagEvaluationRuns: vi.fn().mockResolvedValue([
    {
      id: "eval_run_1",
      triggered_by: "99999999-9999-9999-9999-999999999999",
      total_questions: 5,
      avg_faithfulness: 0.96,
      avg_answer_relevance: 0.92,
      avg_context_recall: 0.95,
      avg_citation_accuracy: 1.0,
      case_results: [
        {
          case_id: "eval_en_01",
          language: "en",
          category: "academic",
          question: "How do I apply for deferment of study?",
          expected_page: 2,
          retrieved_pages: [2],
          answer: "Apply by week 4 [1].",
          faithfulness: 0.96,
          answer_relevance: 0.92,
          context_recall: 1.0,
          citation_accuracy: 1.0,
          passed: true,
        },
      ],
      created_at: "2026-11-08T00:00:00Z",
    },
  ]),
  runRagEvaluation: vi.fn(),
  uploadAdminDocument: vi.fn(),
  updateAdminDocument: vi.fn(),
  deleteAdminDocument: vi.fn(),
  fetchInstitutionalAnalytics: vi.fn().mockResolvedValue({
    total_sessions: 4,
    total_student_queries: 10,
    grounded_answers_count: 9,
    unanswered_queries_count: 1,
    grounding_rate: 0.9,
    estimated_tickets_deflected: 9,
    estimated_hours_saved: 1.8,
    language_distribution: { en: 6, ms: 4 },
    category_breakdown: [{ category: "academic", count: 4 }],
    knowledge_gaps: [
      {
        query: "Is there an overnight shuttle bus to KLIA?",
        language: "en",
        category_filter: "facilities",
        occurrences: 2,
        last_asked_at: "2026-11-08T12:00:00Z",
      },
    ],
  }),
}));

describe("Milestone 5: Admin Knowledge Dashboard & RAG Evaluation Scorecard", () => {
  beforeEach(() => {
    mockCurrentUserRole = "admin";
    vi.clearAllMocks();
  });

  it("renders indexed documents table and RAG Evaluation Scorecard metrics for Admin", async () => {
    render(
      <LanguageProvider>
        <AdminDashboard />
      </LanguageProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("eval-scorecard")).toBeInTheDocument();
    });

    expect(screen.getByTestId("metric-faithfulness")).toHaveTextContent("96%");
    expect(screen.getByTestId("metric-citation-accuracy")).toHaveTextContent(
      "100%"
    );
    expect(screen.getByTestId("documents-table")).toHaveTextContent(
      "Undergraduate Academic Regulations 2026"
    );
    expect(
      screen.getByTestId("institutional-analytics-section")
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("analytics-tickets-deflected")
    ).toHaveTextContent("9");
  });

  it("shows RBAC guard prompt when viewed as a Student role", () => {
    mockCurrentUserRole = "student";
    render(
      <LanguageProvider>
        <AdminDashboard />
      </LanguageProvider>
    );

    expect(
      screen.getByText("Administrator Privileges Required")
    ).toBeInTheDocument();
    const switchBtn = screen.getByTestId("activate-admin-btn");
    fireEvent.click(switchBtn);
    expect(mockLoginWithDemoRole).toHaveBeenCalledWith("admin", "en");
  });
});

