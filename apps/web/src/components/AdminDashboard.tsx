"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  Activity,
  BarChart3,
  CheckCircle2,
  FileText,
  FileUp,
  Loader2,
  Play,
  ShieldAlert,
  ToggleLeft,
  ToggleRight,
  Trash2,
  XCircle,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useLanguage } from "@/context/LanguageContext";
import {
  deleteAdminDocument,
  fetchAdminDocuments,
  fetchInstitutionalAnalytics,
  fetchRagEvaluationRuns,
  runRagEvaluation,
  updateAdminDocument,
  uploadAdminDocument,
} from "@/lib/api";
import {
  DocumentCategory,
  DocumentLanguage,
  DocumentMetadata,
  EvalRunSummary,
  InstitutionalAnalyticsSummary,
} from "@/types/api";

export function AdminDashboard() {
  const { user, token, loginWithDemoRole } = useAuth();
  const { language } = useLanguage();

  const [documents, setDocuments] = useState<DocumentMetadata[]>([]);
  const [evalRuns, setEvalRuns] = useState<EvalRunSummary[]>([]);
  const [analytics, setAnalytics] =
    useState<InstitutionalAnalyticsSummary | null>(null);
  const [isLoadingData, setIsLoadingData] = useState<boolean>(false);

  // Upload Form State
  const [title, setTitle] = useState<string>("");
  const [category, setCategory] = useState<DocumentCategory>("academic");
  const [docLanguage, setDocLanguage] = useState<DocumentLanguage>("bilingual");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState<boolean>(false);

  // Evaluation Runner State
  const [isRunningEval, setIsRunningEval] = useState<boolean>(false);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const isAdmin = user?.role === "admin";

  const loadAdminData = useCallback(async () => {
    if (!token || !isAdmin) return;
    setIsLoadingData(true);
    try {
      const [docs, runs, analyticsData] = await Promise.all([
        fetchAdminDocuments(token),
        fetchRagEvaluationRuns(token),
        fetchInstitutionalAnalytics(token).catch(() => null),
      ]);
      setDocuments(docs);
      setEvalRuns(runs);
      if (analyticsData) setAnalytics(analyticsData);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to load admin resources"
      );
    } finally {
      setIsLoadingData(false);
    }
  }, [token, isAdmin]);

  useEffect(() => {
    loadAdminData();
  }, [loadAdminData]);

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !selectedFile || !title.trim()) return;

    setIsUploading(true);
    setErrorMessage(null);
    setFeedbackMessage(null);

    try {
      const uploaded = await uploadAdminDocument(token, {
        file: selectedFile,
        title: title.trim(),
        category,
        language: docLanguage,
      });
      setDocuments((prev) => [uploaded, ...prev]);
      setTitle("");
      setSelectedFile(null);
      setFeedbackMessage(
        `Indexed "${uploaded.title}" (${uploaded.page_count} pages, ${uploaded.chunk_count} vector chunks).`
      );
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Document upload failed"
      );
    } finally {
      setIsUploading(false);
    }
  };

  const handleToggleActive = async (doc: DocumentMetadata) => {
    if (!token) return;
    try {
      const updated = await updateAdminDocument(token, doc.id, {
        is_active: !doc.is_active,
      });
      setDocuments((prev) =>
        prev.map((d) => (d.id === doc.id ? updated : d))
      );
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to update document status"
      );
    }
  };

  const handleDeleteDocument = async (docId: string) => {
    if (!token) return;
    try {
      await deleteAdminDocument(token, docId);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to delete document"
      );
    }
  };

  const handleRunEvaluation = async () => {
    if (!token || isRunningEval) return;
    setIsRunningEval(true);
    setErrorMessage(null);
    setFeedbackMessage(null);

    try {
      const summary = await runRagEvaluation(token);
      setEvalRuns((prev) => [summary, ...prev]);
      await loadAdminData();
      setFeedbackMessage(
        `Completed RAG Evaluation across ${summary.total_questions} bilingual benchmark questions.`
      );
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "RAG Evaluation failed"
      );
    } finally {
      setIsRunningEval(false);
    }
  };

  if (!isAdmin) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-16 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-100 text-amber-700">
          <ShieldAlert className="h-7 w-7" />
        </div>
        <h1 className="text-xl font-bold text-slate-900">
          Administrator Privileges Required
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          You are currently signed in as a <strong>Student</strong>. Switch to
          the Campus Admin role to upload PDF knowledge sources and run RAG
          faithfulness evaluations.
        </p>
        <button
          type="button"
          onClick={() => loginWithDemoRole("admin", language)}
          data-testid="activate-admin-btn"
          className="mt-6 inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-xs transition hover:bg-indigo-700"
        >
          Switch to Campus Admin Mode (Dr. Farah)
        </button>
      </div>
    );
  }

  const latestEval = evalRuns[0] || null;

  return (
    <div className="mx-auto max-w-7xl space-y-8 px-4 py-8 sm:px-6">
      {/* Header Banner */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Knowledge Base &amp; RAG Evaluation Dashboard
          </h1>
          <p className="text-sm text-slate-600">
            Manage official university PDF sources, ChromaDB vector indexing, and
            bilingual RAG accuracy benchmarks.
          </p>
        </div>
        <button
          type="button"
          onClick={handleRunEvaluation}
          disabled={isRunningEval}
          data-testid="run-eval-btn"
          className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-xs transition hover:bg-indigo-700 disabled:opacity-60"
        >
          {isRunningEval ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          <span>Run RAG Accuracy &amp; Faithfulness Suite</span>
        </button>
      </div>

      {/* Status Alerts */}
      {feedbackMessage && (
        <div
          data-testid="admin-feedback-banner"
          className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs font-medium text-emerald-800"
        >
          {feedbackMessage}
        </div>
      )}
      {errorMessage && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs font-medium text-rose-700">
          {errorMessage}
        </div>
      )}

      {/* Top Grid: PDF Upload Card + RAG Evaluation Scorecard */}
      <div className="grid gap-6 lg:grid-cols-12">
        {/* Upload Form (5 cols) */}
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs lg:col-span-5">
          <div className="mb-4 flex items-center gap-2">
            <FileUp className="h-5 w-5 text-indigo-600" />
            <h2 className="text-base font-bold text-slate-900">
              Upload &amp; Index University PDF
            </h2>
          </div>

          <form onSubmit={handleUploadSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700">
                Document Title
              </label>
              <input
                type="text"
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g., Undergraduate Academic Regulations 2026"
                data-testid="upload-title-input"
                className="mt-1 w-full rounded-xl border border-slate-300 px-3.5 py-2 text-sm text-slate-900 focus:border-indigo-500 focus:outline-hidden"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700">
                  Category
                </label>
                <select
                  value={category}
                  onChange={(e) =>
                    setCategory(e.target.value as DocumentCategory)
                  }
                  className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                >
                  <option value="academic">Academic</option>
                  <option value="facilities">Facilities</option>
                  <option value="events">Events</option>
                  <option value="financial">Financial Aid</option>
                  <option value="general">General</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700">
                  Document Language
                </label>
                <select
                  value={docLanguage}
                  onChange={(e) =>
                    setDocLanguage(e.target.value as DocumentLanguage)
                  }
                  className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                >
                  <option value="bilingual">Bilingual (EN + MS)</option>
                  <option value="en">English (EN)</option>
                  <option value="ms">Bahasa Melayu (MS)</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700">
                PDF File (Max 25 MB)
              </label>
              <input
                type="file"
                accept="application/pdf,.pdf"
                required
                onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                data-testid="upload-file-input"
                className="mt-1 block w-full text-xs text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-3 file:py-2 file:text-xs file:font-semibold file:text-indigo-700 hover:file:bg-indigo-100"
              />
            </div>

            <button
              type="submit"
              disabled={isUploading || !selectedFile || !title.trim()}
              data-testid="upload-submit-btn"
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-xs transition hover:bg-indigo-700 disabled:opacity-50"
            >
              {isUploading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Extracting Pages &amp; Indexing Vectors...</span>
                </>
              ) : (
                <>
                  <FileUp className="h-4 w-4" />
                  <span>Upload &amp; Index Document</span>
                </>
              )}
            </button>
          </form>
        </section>

        {/* RAG Evaluation Scorecard (7 cols) */}
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs lg:col-span-7">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-indigo-600" />
              <h2 className="text-base font-bold text-slate-900">
                RAG Accuracy &amp; Answer Faithfulness Scorecard
              </h2>
            </div>
            {latestEval && (
              <span className="rounded-full bg-emerald-50 px-3 py-0.5 text-xs font-semibold text-emerald-700">
                {latestEval.total_questions} Benchmark Cases
              </span>
            )}
          </div>

          {!latestEval ? (
            <div className="flex h-56 flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 p-6 text-center">
              <p className="text-sm font-medium text-slate-600">
                No RAG Evaluation runs recorded yet.
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Click &ldquo;Run RAG Accuracy &amp; Faithfulness Suite&rdquo; to
                benchmark English and Bahasa Melayu retrieval &amp; page
                citations.
              </p>
            </div>
          ) : (
            <div className="space-y-5" data-testid="eval-scorecard">
              {/* 4 Metric Tiles */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5">
                  <p className="text-xs font-medium text-slate-500">
                    Faithfulness
                  </p>
                  <p
                    className="mt-1 text-xl font-bold text-indigo-700"
                    data-testid="metric-faithfulness"
                  >
                    {Math.round(latestEval.avg_faithfulness * 100)}%
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5">
                  <p className="text-xs font-medium text-slate-500">
                    Answer Relevance
                  </p>
                  <p className="mt-1 text-xl font-bold text-indigo-700">
                    {Math.round(latestEval.avg_answer_relevance * 100)}%
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5">
                  <p className="text-xs font-medium text-slate-500">
                    Context Recall
                  </p>
                  <p className="mt-1 text-xl font-bold text-indigo-700">
                    {Math.round(latestEval.avg_context_recall * 100)}%
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5">
                  <p className="text-xs font-medium text-slate-500">
                    Citation Accuracy
                  </p>
                  <p
                    className="mt-1 text-xl font-bold text-emerald-700"
                    data-testid="metric-citation-accuracy"
                  >
                    {Math.round(latestEval.avg_citation_accuracy * 100)}%
                  </p>
                </div>
              </div>

              {/* Per-Question Breakdown Table */}
              <div className="max-h-56 overflow-y-auto rounded-xl border border-slate-200">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-slate-200 bg-slate-50 text-slate-500">
                    <tr>
                      <th className="px-3 py-2">Case</th>
                      <th className="px-3 py-2">Lang</th>
                      <th className="px-3 py-2">Expected Page</th>
                      <th className="px-3 py-2">Retrieved</th>
                      <th className="px-3 py-2">Faithfulness</th>
                      <th className="px-3 py-2">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {latestEval.case_results.map((c) => (
                      <tr key={c.case_id} className="hover:bg-slate-50">
                        <td className="px-3 py-2 font-medium text-slate-800">
                          {c.question}
                        </td>
                        <td className="px-3 py-2 uppercase">{c.language}</td>
                        <td className="px-3 py-2">Page {c.expected_page}</td>
                        <td className="px-3 py-2">
                          {c.retrieved_pages.map((p) => `p.${p}`).join(", ") ||
                            "-"}
                        </td>
                        <td className="px-3 py-2 font-semibold">
                          {Math.round(c.faithfulness * 100)}%
                        </td>
                        <td className="px-3 py-2">
                          {c.passed ? (
                            <span className="inline-flex items-center gap-1 text-emerald-700 font-semibold">
                              <CheckCircle2 className="h-3.5 w-3.5" />
                              Pass
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-rose-600 font-semibold">
                              <XCircle className="h-3.5 w-3.5" />
                              Review
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      </div>

      {/* Phase 5: Institutional Intelligence & Knowledge Gap Analytics */}
      {analytics && (
        <section
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs"
          data-testid="institutional-analytics-section"
        >
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5 text-indigo-600" />
              <h2 className="text-base font-bold text-slate-900">
                Institutional ROI &amp; Knowledge Gap Detection
              </h2>
            </div>
            <span className="rounded-full bg-indigo-50 px-3 py-0.5 text-xs font-semibold text-indigo-700">
              Grounding Rate: {Math.round(analytics.grounding_rate * 100)}%
            </span>
          </div>

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-medium text-slate-500">
                Student Inquiries
              </p>
              <p className="mt-1 text-2xl font-bold text-slate-900">
                {analytics.total_student_queries}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-medium text-slate-500">
                Support Tickets Deflected
              </p>
              <p
                className="mt-1 text-2xl font-bold text-emerald-700"
                data-testid="analytics-tickets-deflected"
              >
                {analytics.estimated_tickets_deflected}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-medium text-slate-500">
                Staff Hours Saved
              </p>
              <p className="mt-1 text-2xl font-bold text-indigo-700">
                {analytics.estimated_hours_saved} hrs
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-medium text-slate-500">
                Detected Policy Gaps
              </p>
              <p className="mt-1 text-2xl font-bold text-amber-600">
                {analytics.knowledge_gaps.length}
              </p>
            </div>
          </div>

          {analytics.knowledge_gaps.length > 0 && (
            <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/50 p-4">
              <p className="text-xs font-bold uppercase tracking-wider text-amber-800">
                Unanswered Student Queries (Actionable Documentation Gaps)
              </p>
              <ul className="mt-2 space-y-1.5 text-xs text-slate-700">
                {analytics.knowledge_gaps.map((gap, idx) => (
                  <li key={idx} className="flex items-center justify-between">
                    <span className="font-medium">&ldquo;{gap.query}&rdquo;</span>
                    <span className="rounded bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-900">
                      {gap.language.toUpperCase()} • {gap.occurrences}x
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {/* Knowledge Sources Table */}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-indigo-600" />
            <h2 className="text-base font-bold text-slate-900">
              Indexed Knowledge Base Documents ({documents.length})
            </h2>
          </div>
          {isLoadingData && (
            <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
          )}
        </div>

        {documents.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-400">
            No documents uploaded yet. Upload a PDF above or click &ldquo;Run
            RAG Accuracy &amp; Faithfulness Suite&rdquo; to auto-seed the sample
            campus corpus.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm" data-testid="documents-table">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Document Title</th>
                  <th className="px-4 py-3">Category</th>
                  <th className="px-4 py-3">Lang</th>
                  <th className="px-4 py-3">Pages</th>
                  <th className="px-4 py-3">Vector Chunks</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Active in RAG</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {documents.map((doc) => (
                  <tr key={doc.id} className="hover:bg-slate-50/70">
                    <td className="px-4 py-3">
                      <p className="font-semibold text-slate-900">{doc.title}</p>
                      <p className="text-xs text-slate-400">{doc.filename}</p>
                    </td>
                    <td className="px-4 py-3 capitalize">{doc.category}</td>
                    <td className="px-4 py-3 uppercase text-xs font-semibold">
                      {doc.language}
                    </td>
                    <td className="px-4 py-3">{doc.page_count}</td>
                    <td className="px-4 py-3">{doc.chunk_count}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                          doc.status === "indexed"
                            ? "bg-emerald-50 text-emerald-700"
                            : doc.status === "failed"
                            ? "bg-rose-50 text-rose-700"
                            : "bg-amber-50 text-amber-700"
                        }`}
                      >
                        {doc.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => handleToggleActive(doc)}
                        data-testid={`toggle-active-${doc.id}`}
                        className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-700"
                      >
                        {doc.is_active ? (
                          <>
                            <ToggleRight className="h-5 w-5 text-emerald-600" />
                            <span>Active</span>
                          </>
                        ) : (
                          <>
                            <ToggleLeft className="h-5 w-5 text-slate-400" />
                            <span className="text-slate-400">Paused</span>
                          </>
                        )}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => handleDeleteDocument(doc.id)}
                        data-testid={`delete-doc-${doc.id}`}
                        className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                        title="Delete Document & Vectors"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

