"use client";

import React from "react";
import {
  AlertTriangle,
  BookOpenCheck,
  CheckCircle2,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { useLanguage } from "@/context/LanguageContext";
import { ChatMessage, Citation } from "@/types/api";

interface MessageItemProps {
  message: ChatMessage;
  onSelectCitation: (citation: Citation) => void;
  onFeedback?: (messageId: string, rating: -1 | 1) => void;
}

export function MessageItem({
  message,
  onSelectCitation,
  onFeedback,
}: MessageItemProps) {
  const { t } = useLanguage();
  const isUser = message.role === "user";

  /**
   * Parse inline citation markers like `[1]`, `[2]` and replace with interactive buttons.
   */
  const renderContentWithCitations = (text: string, citations: Citation[]) => {
    const parts = text.split(/(\[\d+\])/g);
    return parts.map((part, idx) => {
      const match = part.match(/^\[(\d+)\]$/);
      if (match) {
        const citationIdx = parseInt(match[1], 10);
        const found = citations.find((c) => c.citation_index === citationIdx);
        if (found) {
          return (
            <button
              key={`${part}-${idx}`}
              type="button"
              onClick={() => onSelectCitation(found)}
              data-testid={`inline-citation-${citationIdx}`}
              className="mx-0.5 inline-flex items-center gap-0.5 rounded-md bg-indigo-100 px-1.5 py-0.5 text-xs font-bold text-indigo-700 transition hover:bg-indigo-600 hover:text-white"
              title={`${found.document_title} (${t.pageLabel} ${found.page_number})`}
            >
              [{citationIdx}]
            </button>
          );
        }
      }
      return <span key={idx}>{part}</span>;
    });
  };

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-2xl rounded-2xl rounded-br-xs bg-indigo-600 px-4 py-3 text-sm text-white shadow-xs">
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

  const hasCitations = message.citations && message.citations.length > 0;

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-3xl space-y-3 rounded-2xl rounded-bl-xs border border-slate-200 bg-white p-5 shadow-xs">
        {/* Grounding Status Header */}
        <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
          <div className="flex items-center gap-2">
            {hasCitations ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700">
                <CheckCircle2 className="h-3.5 w-3.5" />
                {t.groundedBadge}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-700">
                <AlertTriangle className="h-3.5 w-3.5" />
                {t.ungroundedBadge}
              </span>
            )}
            <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-semibold uppercase text-slate-600">
              {message.detected_language === "ms" ? "Bahasa Melayu" : "English"}
            </span>
          </div>

          {message.latency_ms && (
            <span className="text-[11px] text-slate-400">
              {message.latency_ms} ms
            </span>
          )}
        </div>

        {/* Message Answer Body */}
        <div
          className="text-sm leading-relaxed text-slate-800 whitespace-pre-wrap"
          data-testid="assistant-message-content"
        >
          {renderContentWithCitations(message.content, message.citations)}
        </div>

        {/* Page Reference Cards */}
        {hasCitations && (
          <div className="space-y-2 pt-2">
            <p className="flex items-center gap-1.5 text-xs font-semibold text-slate-500">
              <BookOpenCheck className="h-3.5 w-3.5 text-indigo-600" />
              {t.sourcesHeader}
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {message.citations.map((cit) => (
                <button
                  key={`${cit.document_id}_${cit.page_number}_${cit.citation_index}`}
                  type="button"
                  onClick={() => onSelectCitation(cit)}
                  data-testid={`citation-card-${cit.citation_index}`}
                  className="flex flex-col items-start rounded-xl border border-slate-200 bg-slate-50/70 p-3 text-left transition hover:border-indigo-300 hover:bg-indigo-50/40"
                >
                  <div className="flex w-full items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1.5 text-xs font-bold text-indigo-700">
                      <span className="rounded bg-indigo-100 px-1.5 py-0.5">
                        [{cit.citation_index}]
                      </span>
                      <span className="line-clamp-1 text-slate-900">
                        {cit.document_title}
                      </span>
                    </span>
                    <span className="shrink-0 rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-slate-700 shadow-2xs">
                      {t.pageLabel} {cit.page_number}
                    </span>
                  </div>
                  <p className="mt-1.5 line-clamp-2 text-xs text-slate-600">
                    {cit.snippet}
                  </p>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Feedback Footer */}
        {onFeedback && (
          <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-2">
            <button
              type="button"
              onClick={() => onFeedback(message.id, 1)}
              className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs transition ${
                message.feedback_rating === 1
                  ? "bg-emerald-100 font-semibold text-emerald-800"
                  : "text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              }`}
              title={t.feedbackHelpful}
            >
              <ThumbsUp className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => onFeedback(message.id, -1)}
              className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs transition ${
                message.feedback_rating === -1
                  ? "bg-rose-100 font-semibold text-rose-800"
                  : "text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              }`}
              title={t.feedbackNotHelpful}
            >
              <ThumbsDown className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

