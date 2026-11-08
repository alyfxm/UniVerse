"use client";

import React, { useEffect, useState } from "react";
import { ExternalLink, FileText, Highlighter, Sparkles, X } from "lucide-react";
import { BACKEND_ORIGIN, fetchPageHighlightPreview } from "@/lib/api";
import { useLanguage } from "@/context/LanguageContext";
import { Citation, PagePreviewResponse } from "@/types/api";

interface CitationDrawerProps {
  citation: Citation | null;
  token?: string | null;
  onClose: () => void;
}

export function CitationDrawer({
  citation,
  token,
  onClose,
}: CitationDrawerProps) {
  const { t } = useLanguage();
  const [pagePreview, setPagePreview] = useState<PagePreviewResponse | null>(
    null
  );

  useEffect(() => {
    let active = true;
    setPagePreview(null);

    if (citation && token) {
      fetchPageHighlightPreview(
        token,
        citation.document_id,
        citation.page_number,
        citation.snippet
      )
        .then((res) => {
          if (active) setPagePreview(res);
        })
        .catch(() => {
          if (active) setPagePreview(null);
        });
    }

    return () => {
      active = false;
    };
  }, [citation, token]);

  if (!citation) return null;

  const fullPdfUrl = citation.file_url.startsWith("http")
    ? citation.file_url
    : `${BACKEND_ORIGIN}${citation.file_url}`;

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-900/40 backdrop-blur-xs"
      data-testid="citation-drawer"
    >
      <div className="flex h-full w-full max-w-xl flex-col bg-white shadow-2xl">
        {/* Drawer Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600 text-xs font-bold text-white">
              [{citation.citation_index}]
            </span>
            <div>
              <h3 className="text-sm font-semibold text-slate-900">
                {citation.document_title}
              </h3>
              <p className="text-xs text-slate-500">
                {t.pageLabel} {citation.page_number} • {t.relevanceLabel}:{" "}
                {Math.round(citation.relevance_score * 100)}%
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            data-testid="close-citation-drawer"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label={t.closePreview}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Drawer Body */}
        <div className="flex-1 space-y-5 overflow-y-auto p-6">
          {/* Highlighted Excerpt Box */}
          <div className="rounded-xl border border-indigo-100 bg-indigo-50/60 p-4">
            <div className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-indigo-700">
              <span className="inline-flex items-center gap-1.5">
                <Sparkles className="h-3.5 w-3.5" />
                {t.sourcesHeader} — {t.pageLabel} {citation.page_number}
              </span>
              <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[11px] font-bold text-indigo-800">
                {citation.category}
              </span>
            </div>
            <blockquote
              className="text-sm leading-relaxed text-slate-800"
              data-testid="citation-snippet-text"
            >
              <mark className="rounded bg-yellow-200/80 px-1 py-0.5 text-slate-900">
                &ldquo;{citation.snippet}&rdquo;
              </mark>
            </blockquote>
          </div>

          {/* Direct PDF Page Viewer Link & Visual Bounding-Box Highlighter */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-600">
                {pagePreview ? (
                  <>
                    <Highlighter className="h-4 w-4 text-amber-500" />
                    <span>
                      Visual Bounding-Box Highlight ({t.pageLabel}{" "}
                      {citation.page_number} of {pagePreview.total_pages})
                    </span>
                  </>
                ) : (
                  <>
                    <FileText className="h-4 w-4 text-slate-400" />
                    <span>
                      PDF Document Reference ({t.pageLabel}{" "}
                      {citation.page_number})
                    </span>
                  </>
                )}
              </span>
              <a
                href={fullPdfUrl}
                target="_blank"
                rel="noopener noreferrer"
                data-testid="citation-pdf-link"
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow-xs transition hover:bg-indigo-700"
              >
                <span>{t.openPdfPage}</span>
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </div>

            <div className="h-96 overflow-auto rounded-xl border border-slate-200 bg-slate-100 p-2">
              {pagePreview?.image_data_url ? (
                <img
                  src={pagePreview.image_data_url}
                  alt={`${citation.document_title} - ${t.pageLabel} ${citation.page_number}`}
                  data-testid="citation-highlighted-page-img"
                  className="mx-auto max-w-full rounded shadow-xs"
                />
              ) : (
                <iframe
                  src={fullPdfUrl}
                  title={`${citation.document_title} - ${t.pageLabel} ${citation.page_number}`}
                  className="h-full w-full rounded"
                />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
