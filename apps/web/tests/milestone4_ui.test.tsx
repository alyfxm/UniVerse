import React, { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CitationDrawer } from "@/components/CitationDrawer";
import { MessageItem } from "@/components/MessageItem";
import { LanguageProvider, useLanguage } from "@/context/LanguageContext";
import { ChatMessage, Citation } from "@/types/api";

const sampleCitation: Citation = {
  citation_index: 1,
  document_id: "doc_102",
  document_title: "Buku Peraturan Akademik Prasiswazah 2026",
  category: "academic",
  page_number: 14,
  snippet:
    "Pelajar yang ingin menangguhkan pengajian hendaklah memohon secara rasmi sebelum tamat minggu keempat (4) kuliah.",
  relevance_score: 0.91,
  file_url: "/api/v1/documents/doc_102/file#page=14",
};

const sampleAssistantMessage: ChatMessage = {
  id: "msg_1",
  session_id: "sess_1",
  role: "assistant",
  content:
    "Untuk memohon penangguhan pengajian, pelajar perlu memohon sebelum minggu ke-4 semester [1].",
  detected_language: "ms",
  citations: [sampleCitation],
  latency_ms: 420,
  created_at: "2026-11-08T10:00:00Z",
};

function InteractiveMessageHarness() {
  const [selected, setSelected] = useState<Citation | null>(null);
  const { language, setLanguage, t } = useLanguage();

  return (
    <div>
      <button
        type="button"
        data-testid="harness-lang-switch"
        onClick={() => setLanguage(language === "en" ? "ms" : "en")}
      >
        {t.tagline}
      </button>
      <MessageItem
        message={sampleAssistantMessage}
        onSelectCitation={(c) => setSelected(c)}
      />
      <CitationDrawer citation={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

describe("Milestone 4: Bilingual UI & Page Citation Drawer", () => {
  it("renders inline [1] citation button and opens the PDF Page Citation Drawer with #page=14", () => {
    render(
      <LanguageProvider>
        <InteractiveMessageHarness />
      </LanguageProvider>
    );

    // Verify inline citation badge [1] is rendered
    const inlineBtn = screen.getByTestId("inline-citation-1");
    expect(inlineBtn).toBeInTheDocument();
    expect(inlineBtn).toHaveTextContent("[1]");

    // Clicking [1] opens the CitationDrawer
    fireEvent.click(inlineBtn);
    const drawer = screen.getByTestId("citation-drawer");
    expect(drawer).toBeInTheDocument();
    expect(screen.getByTestId("citation-snippet-text")).toHaveTextContent(
      "minggu keempat (4)"
    );

    const pdfLink = screen.getByTestId("citation-pdf-link");
    expect(pdfLink).toHaveAttribute(
      "href",
      expect.stringContaining("/api/v1/documents/doc_102/file#page=14")
    );

    // Closing drawer hides it
    fireEvent.click(screen.getByTestId("close-citation-drawer"));
    expect(screen.queryByTestId("citation-drawer")).not.toBeInTheDocument();
  });

  it("switches UI dictionary strings between English (EN) and Bahasa Melayu (MS)", () => {
    render(
      <LanguageProvider>
        <InteractiveMessageHarness />
      </LanguageProvider>
    );

    const langBtn = screen.getByTestId("harness-lang-switch");
    expect(langBtn).toHaveTextContent("Multilingual AI Campus Assistant");

    fireEvent.click(langBtn);
    expect(langBtn).toHaveTextContent("Pembantu Kampus AI Dwibahasa");
    expect(
      screen.getByText("Disahkan daripada Dokumen Rasmi")
    ).toBeInTheDocument();
  });

  it("calls onFeedback handler when thumbs-up button is clicked", () => {
    const onFeedbackMock = vi.fn();
    render(
      <LanguageProvider>
        <MessageItem
          message={sampleAssistantMessage}
          onSelectCitation={() => {}}
          onFeedback={onFeedbackMock}
        />
      </LanguageProvider>
    );

    const helpfulBtn = screen.getByTitle("Helpful answer");
    fireEvent.click(helpfulBtn);
    expect(onFeedbackMock).toHaveBeenCalledWith("msg_1", 1);
  });
});

