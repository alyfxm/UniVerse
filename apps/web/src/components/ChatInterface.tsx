"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  CalendarCheck,
  FileDown,
  Filter,
  GraduationCap,
  Loader2,
  MessageSquarePlus,
  Send,
  Sparkles,
  Trash2,
} from "lucide-react";
import { CitationDrawer } from "@/components/CitationDrawer";
import { MessageItem } from "@/components/MessageItem";
import { useAuth } from "@/context/AuthContext";
import { useLanguage } from "@/context/LanguageContext";
import {
  API_BASE_URL,
  bookAcademicAdvisor,
  deleteChatSession,
  fetchChatSessionDetail,
  fetchChatSessions,
  fetchStudentSisProfile,
  streamChatQuery,
  submitMessageFeedback,
} from "@/lib/api";
import {
  CategoryFilter,
  ChatMessage,
  ChatSessionSummary,
  Citation,
  StudentSisProfile,
} from "@/types/api";

const CATEGORY_KEYS: CategoryFilter[] = [
  "all",
  "academic",
  "facilities",
  "events",
  "financial",
  "general",
];

export function ChatInterface() {
  const { token, user } = useAuth();
  const { language, t } = useLanguage();

  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [queryInput, setQueryInput] = useState<string>("");
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>("all");
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [streamingContent, setStreamingContent] = useState<string>("");
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(
    null
  );
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [sisProfile, setSisProfile] = useState<StudentSisProfile | null>(null);
  const [agentNotice, setAgentNotice] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const loadSessions = useCallback(async () => {
    if (!token) return;
    try {
      const list = await fetchChatSessions(token);
      setSessions(list);
    } catch {
      // Ignore initial list error when backend is offline
    }
  }, [token]);

  useEffect(() => {
    loadSessions();
    if (token) {
      fetchStudentSisProfile(token)
        .then((profile) => setSisProfile(profile))
        .catch(() => {});
    }
  }, [loadSessions, token]);

  useEffect(() => {
    if (
      messagesEndRef.current &&
      typeof messagesEndRef.current.scrollIntoView === "function"
    ) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, streamingContent]);

  const handleSelectSession = async (sessionId: string) => {
    if (!token) return;
    setErrorBanner(null);
    try {
      const detail = await fetchChatSessionDetail(token, sessionId);
      setActiveSessionId(detail.session.id);
      setMessages(detail.messages);
      setCategoryFilter(detail.session.category_filter || "all");
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : "Failed to load session"
      );
    }
  };

  const handleNewChat = () => {
    setActiveSessionId(null);
    setMessages([]);
    setSelectedCitation(null);
    setErrorBanner(null);
  };

  const handleDeleteSession = async (
    e: React.MouseEvent,
    sessionId: string
  ) => {
    e.stopPropagation();
    if (!token) return;
    try {
      await deleteChatSession(token, sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (activeSessionId === sessionId) {
        handleNewChat();
      }
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : "Failed to delete session"
      );
    }
  };

  const handleSendQuery = async (customQuery?: string) => {
    const textToSend = (customQuery ?? queryInput).trim();
    if (!textToSend || !token || isStreaming) return;

    setQueryInput("");
    setErrorBanner(null);

    const optimisticUserMsg: ChatMessage = {
      id: `temp_user_${Date.now()}`,
      session_id: activeSessionId || "pending",
      role: "user",
      content: textToSend,
      detected_language: language,
      citations: [],
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, optimisticUserMsg]);
    setIsStreaming(true);
    setStreamingContent("");

    try {
      const finalRes = await streamChatQuery(
        token,
        {
          session_id: activeSessionId,
          query: textToSend,
          language: "auto",
          category_filter: categoryFilter,
        },
        (delta) => {
          setStreamingContent((prev) => prev + delta);
        }
      );

      setActiveSessionId(finalRes.session_id);
      const assistantMsg: ChatMessage = {
        id: finalRes.message_id,
        session_id: finalRes.session_id,
        role: "assistant",
        content: finalRes.answer,
        detected_language: finalRes.detected_language,
        citations: finalRes.citations,
        latency_ms: finalRes.latency_ms,
        created_at: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, assistantMsg]);
      setStreamingContent("");
      await loadSessions();
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : "Unable to reach UniVerse AI API"
      );
    } finally {
      setIsStreaming(false);
    }
  };

  const handleFeedback = async (messageId: string, rating: -1 | 1) => {
    if (!token) return;
    try {
      const updated = await submitMessageFeedback(token, messageId, rating);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === messageId
            ? { ...m, feedback_rating: updated.feedback_rating }
            : m
        )
      );
    } catch {
      // Ignore feedback error
    }
  };

  const handleBookAdvisorAction = async () => {
    if (!token) return;
    try {
      const apt = await bookAcademicAdvisor(token, {
        topic: "Course Registration & Elective Prerequisite Review",
        preferred_slot: "Thursday, 14:00 - 14:30 MYT",
      });
      setAgentNotice(
        `Confirmed Advisor Slot (${apt.appointment_id}): ${apt.advisor_name} on ${apt.preferred_slot}`
      );
    } catch (err) {
      setErrorBanner(
        err instanceof Error ? err.message : "Failed to book advisor"
      );
    }
  };

  const handleDownloadPrefilledForm = async () => {
    if (!token) return;
    try {
      const res = await fetch(
        `${API_BASE_URL}/student/agent/deferment-form/pdf`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            reason_category: "medical",
            supporting_details:
              "Official Hospital Medical Certificate attached for Semester 1.",
          }),
        }
      );
      if (res.ok) {
        setAgentNotice(
          "Generated SIS Pre-Filled Deferment Application PDF (U20251048)."
        );
      }
    } catch {
      // Ignore in offline test
    }
  };

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden bg-slate-50">
      {/* Left Sidebar: Session History */}
      <aside className="hidden w-72 shrink-0 flex-col border-r border-slate-200 bg-white md:flex">
        <div className="p-4">
          <button
            type="button"
            onClick={handleNewChat}
            data-testid="new-chat-btn"
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-xs transition hover:bg-indigo-700"
          >
            <MessageSquarePlus className="h-4 w-4" />
            <span>{t.newChat}</span>
          </button>
        </div>

        <div className="px-4 pb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
          {t.chatHistory}
        </div>

        <div className="flex-1 space-y-1 overflow-y-auto px-3 pb-4">
          {sessions.length === 0 ? (
            <p className="px-2 py-6 text-center text-xs text-slate-400">
              {t.noSessions}
            </p>
          ) : (
            sessions.map((sess) => {
              const isSelected = sess.id === activeSessionId;
              return (
                <div
                  key={sess.id}
                  onClick={() => handleSelectSession(sess.id)}
                  className={`group flex cursor-pointer items-center justify-between rounded-xl px-3 py-2.5 text-sm transition ${
                    isSelected
                      ? "bg-indigo-50 font-semibold text-indigo-700"
                      : "text-slate-700 hover:bg-slate-100"
                  }`}
                >
                  <div className="min-w-0 flex-1 pr-2">
                    <p className="truncate">{sess.title}</p>
                    <p className="text-[11px] text-slate-400">
                      {sess.language.toUpperCase()} • {sess.category_filter}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => handleDeleteSession(e, sess.id)}
                    className="opacity-0 rounded-md p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600 group-hover:opacity-100"
                    aria-label="Delete session"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              );
            })
          )}
        </div>

        {/* User Footer */}
        {user && (
          <div className="border-t border-slate-200 p-4 text-xs text-slate-600">
            <p className="font-semibold text-slate-900">{user.display_name}</p>
            <p className="truncate text-slate-400">{user.email}</p>
          </div>
        )}
      </aside>

      {/* Main Chat Area */}
      <main className="flex flex-1 flex-col overflow-hidden">
        {/* Category Filter Bar + Agentic Quick Tools */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-white px-4 py-2.5 sm:px-6">
          <div className="flex items-center gap-2 overflow-x-auto">
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500">
              <Filter className="h-3.5 w-3.5 text-indigo-600" />
            </span>
            {CATEGORY_KEYS.map((cat) => {
              const active = categoryFilter === cat;
              return (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setCategoryFilter(cat)}
                  data-testid={`category-pill-${cat}`}
                  className={`shrink-0 rounded-full px-3 py-1 text-xs font-semibold transition ${
                    active
                      ? "bg-indigo-600 text-white shadow-2xs"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {t.categories[cat]}
                </button>
              );
            })}
          </div>

          {/* Phase 4: SIS Context Badge & Agentic Tool Actions */}
          <div className="flex items-center gap-2">
            {sisProfile && (
              <span
                data-testid="sis-profile-badge"
                className="hidden items-center gap-1.5 rounded-lg border border-indigo-100 bg-indigo-50/70 px-2.5 py-1 text-xs font-medium text-indigo-800 lg:inline-flex"
              >
                <GraduationCap className="h-3.5 w-3.5 text-indigo-600" />
                <span>
                  {sisProfile.matric_number} • Yr {sisProfile.study_year} • CGPA{" "}
                  {sisProfile.cgpa}
                </span>
              </span>
            )}
            <button
              type="button"
              onClick={handleBookAdvisorAction}
              data-testid="agent-book-advisor-btn"
              className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-700 transition hover:bg-indigo-50 hover:text-indigo-700"
            >
              <CalendarCheck className="h-3.5 w-3.5 text-indigo-600" />
              <span>Book Advisor</span>
            </button>
            <button
              type="button"
              onClick={handleDownloadPrefilledForm}
              data-testid="agent-prefill-form-btn"
              className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-700 transition hover:bg-indigo-50 hover:text-indigo-700"
            >
              <FileDown className="h-3.5 w-3.5 text-indigo-600" />
              <span>Auto-Fill Deferment PDF</span>
            </button>
          </div>
        </div>

        {agentNotice && (
          <div
            data-testid="agent-action-notice"
            className="mx-6 mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs font-medium text-emerald-800"
          >
            {agentNotice}
          </div>
        )}

        {/* Error Alert */}
        {errorBanner && (
          <div className="mx-6 mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs font-medium text-rose-700">
            {errorBanner}
          </div>
        )}

        {/* Messages or Empty Starter State */}
        <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
          {messages.length === 0 && !isStreaming ? (
            <div className="mx-auto flex max-w-2xl flex-col items-center justify-center py-12 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-md">
                <Sparkles className="h-7 w-7" />
              </div>
              <h1 className="text-2xl font-bold text-slate-900">
                {t.signInTitle}
              </h1>
              <p className="mt-1 max-w-md text-sm text-slate-600">
                {t.tagline} — Bahasa Melayu &amp; English
              </p>

              {/* Starter Prompts Grid */}
              <div className="mt-8 grid w-full gap-3 sm:grid-cols-2">
                {t.starterPrompts.map((item, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => {
                      setCategoryFilter(item.category);
                      handleSendQuery(item.prompt);
                    }}
                    data-testid={`starter-prompt-${idx}`}
                    className="flex flex-col items-start rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-2xs transition hover:border-indigo-300 hover:shadow-sm"
                  >
                    <span className="rounded-md bg-indigo-50 px-2 py-0.5 text-[11px] font-bold uppercase text-indigo-700">
                      {t.categories[item.category]}
                    </span>
                    <span className="mt-2 text-sm font-semibold text-slate-900">
                      {item.title}
                    </span>
                    <span className="mt-1 line-clamp-2 text-xs text-slate-500">
                      {item.prompt}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-6">
              {messages.map((msg) => (
                <MessageItem
                  key={msg.id}
                  message={msg}
                  onSelectCitation={(cit) => setSelectedCitation(cit)}
                  onFeedback={handleFeedback}
                />
              ))}

              {isStreaming && (
                <div className="flex justify-start">
                  <div className="w-full max-w-3xl space-y-2 rounded-2xl border border-indigo-100 bg-white p-5 shadow-xs">
                    <div className="flex items-center gap-2 text-xs font-medium text-indigo-600">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>{t.generating}</span>
                    </div>
                    {streamingContent && (
                      <p className="text-sm leading-relaxed text-slate-800 whitespace-pre-wrap">
                        {streamingContent}
                      </p>
                    )}
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Bottom Composer */}
        <div className="border-t border-slate-200 bg-white p-4 sm:px-6">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendQuery();
            }}
            className="mx-auto flex max-w-3xl items-center gap-3"
          >
            <input
              type="text"
              value={queryInput}
              onChange={(e) => setQueryInput(e.target.value)}
              placeholder={t.askPlaceholder}
              disabled={isStreaming}
              data-testid="chat-input"
              className="flex-1 rounded-xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:bg-white focus:outline-hidden"
            />
            <button
              type="submit"
              disabled={isStreaming || !queryInput.trim()}
              data-testid="chat-submit-btn"
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white shadow-xs transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span>{t.sendButton}</span>
              <Send className="h-4 w-4" />
            </button>
          </form>
        </div>
      </main>

      {/* Slide-over PDF Citation Drawer */}
      <CitationDrawer
        citation={selectedCitation}
        token={token}
        onClose={() => setSelectedCitation(null)}
      />
    </div>
  );
}

