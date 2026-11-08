"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  Globe,
  GraduationCap,
  MessageSquare,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useLanguage } from "@/context/LanguageContext";

export function Navbar() {
  const pathname = usePathname();
  const { user, loginWithDemoRole } = useAuth();
  const { language, setLanguage, t } = useLanguage();

  const toggleLanguage = () => {
    const nextLang = language === "en" ? "ms" : "en";
    setLanguage(nextLang);
  };

  const toggleDemoRole = async () => {
    const nextRole = user?.role === "admin" ? "student" : "admin";
    await loginWithDemoRole(nextRole, language);
  };

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
        {/* Brand Logo */}
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm">
              <GraduationCap className="h-6 w-6" />
            </div>
            <div>
              <span className="text-lg font-bold tracking-tight text-slate-900">
                {t.appName}
              </span>
              <span className="hidden text-xs text-slate-500 sm:block">
                {t.tagline}
              </span>
            </div>
          </Link>
        </div>

        {/* Navigation Links & Controls */}
        <div className="flex items-center gap-2 sm:gap-3">
          <Link
            href="/"
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
              pathname === "/"
                ? "bg-indigo-50 text-indigo-700"
                : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            }`}
          >
            <MessageSquare className="h-4 w-4" />
            <span>{t.studentChat}</span>
          </Link>

          <Link
            href="/admin"
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
              pathname?.startsWith("/admin")
                ? "bg-indigo-50 text-indigo-700"
                : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            }`}
          >
            <BookOpen className="h-4 w-4" />
            <span>{t.adminDashboard}</span>
          </Link>

          {/* Language Switcher (EN / MS) */}
          <button
            type="button"
            onClick={toggleLanguage}
            data-testid="language-toggle-btn"
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-100"
            title="Switch Language (English / Bahasa Melayu)"
          >
            <Globe className="h-3.5 w-3.5 text-indigo-600" />
            <span>{language === "en" ? "EN • English" : "MS • Bahasa Melayu"}</span>
          </button>

          {/* Role Switcher (Student / Admin) */}
          {user && (
            <button
              type="button"
              onClick={toggleDemoRole}
              data-testid="role-toggle-btn"
              className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
                user.role === "admin"
                  ? "border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100"
                  : "border-emerald-200 bg-emerald-50 text-emerald-800 hover:bg-emerald-100"
              }`}
              title="Switch Role between Student & Campus Admin"
            >
              {user.role === "admin" ? (
                <>
                  <ShieldCheck className="h-3.5 w-3.5" />
                  <span>{t.switchRoleAdmin}</span>
                </>
              ) : (
                <>
                  <UserCheck className="h-3.5 w-3.5" />
                  <span>{t.switchRoleStudent}</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </header>
  );
}

