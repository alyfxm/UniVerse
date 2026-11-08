/**
 * Bilingual UI Dictionary (English `en` & Bahasa Melayu `ms`) for UniVerse.
 */

import { CategoryFilter, SupportedLanguage } from "@/types/api";

export interface UiTranslations {
  appName: string;
  tagline: string;
  newChat: string;
  chatHistory: string;
  noSessions: string;
  askPlaceholder: string;
  sendButton: string;
  generating: string;
  groundedBadge: string;
  ungroundedBadge: string;
  sourcesHeader: string;
  pageLabel: string;
  openPdfPage: string;
  closePreview: string;
  relevanceLabel: string;
  adminDashboard: string;
  studentChat: string;
  switchRoleStudent: string;
  switchRoleAdmin: string;
  signInTitle: string;
  signInSubtitle: string;
  demoStudentBtn: string;
  demoAdminBtn: string;
  categories: Record<CategoryFilter, string>;
  starterPrompts: {
    category: CategoryFilter;
    title: string;
    prompt: string;
  }[];
  feedbackHelpful: string;
  feedbackNotHelpful: string;
}

export const DICTIONARY: Record<SupportedLanguage, UiTranslations> = {
  en: {
    appName: "UniVerse",
    tagline: "Multilingual AI Campus Assistant",
    newChat: "New Conversation",
    chatHistory: "Recent Conversations",
    noSessions: "No conversations yet. Ask a campus question below!",
    askPlaceholder:
      "Ask about academic policies, library hours, hostel, or scholarships (English or Bahasa Melayu)...",
    sendButton: "Send",
    generating: "Searching official campus documents & verifying citations...",
    groundedBadge: "Verified Campus Source",
    ungroundedBadge: "Unverified / Not in Official Docs",
    sourcesHeader: "Page References & Citations",
    pageLabel: "Page",
    openPdfPage: "View Original PDF Page",
    closePreview: "Close Document Preview",
    relevanceLabel: "Match",
    adminDashboard: "Knowledge Admin",
    studentChat: "Student Assistant",
    switchRoleStudent: "Student View",
    switchRoleAdmin: "Admin Mode",
    signInTitle: "Welcome to UniVerse",
    signInSubtitle:
      "Sign in with your university account or launch an instant demo session.",
    demoStudentBtn: "Continue as Student (Aiman)",
    demoAdminBtn: "Continue as Campus Admin (Dr. Farah)",
    categories: {
      all: "All Topics",
      academic: "Academic",
      facilities: "Facilities",
      events: "Events",
      financial: "Financial Aid",
      general: "General",
    },
    starterPrompts: [
      {
        category: "academic",
        title: "Deferment of Study",
        prompt: "How do I apply for deferment of study and what is the deadline?",
      },
      {
        category: "facilities",
        title: "Library Operating Hours",
        prompt: "What are the main university library operating hours?",
      },
      {
        category: "academic",
        title: "Penangguhan Pengajian (BM)",
        prompt: "Bagaimanakah cara memohon penangguhan pengajian atas sebab kesihatan?",
      },
      {
        category: "facilities",
        title: "Kolej Kediaman & Asrama (BM)",
        prompt: "Siapakah yang layak memohon bilik kolej kediaman asrama?",
      },
    ],
    feedbackHelpful: "Helpful answer",
    feedbackNotHelpful: "Needs improvement",
  },
  ms: {
    appName: "UniVerse",
    tagline: "Pembantu Kampus AI Dwibahasa",
    newChat: "Perbualan Baharu",
    chatHistory: "Sejarah Perbualan",
    noSessions: "Tiada sejarah perbualan. Tanya soalan kampus di bawah!",
    askPlaceholder:
      "Tanya mengenai peraturan akademik, waktu perpustakaan, asrama, atau biasiswa (BM atau Inggeris)...",
    sendButton: "Hantar",
    generating: "Mencari dokumen rasmi universiti & mengesahkan rujukan halaman...",
    groundedBadge: "Disahkan daripada Dokumen Rasmi",
    ungroundedBadge: "Tiada dalam Dokumen Rasmi",
    sourcesHeader: "Rujukan Dokumen & Halaman Asal",
    pageLabel: "Halaman",
    openPdfPage: "Lihat Halaman PDF Asal",
    closePreview: "Tutup Pratonton Dokumen",
    relevanceLabel: "Padanan",
    adminDashboard: "Papan Pemuka Admin",
    studentChat: "Pembantu Pelajar",
    switchRoleStudent: "Mod Pelajar",
    switchRoleAdmin: "Mod Admin",
    signInTitle: "Selamat Datang ke UniVerse",
    signInSubtitle:
      "Log masuk menggunakan akaun universiti anda atau gunakan sesi demo pantas.",
    demoStudentBtn: "Masuk sebagai Pelajar (Aiman)",
    demoAdminBtn: "Masuk sebagai Admin Kampus (Dr. Farah)",
    categories: {
      all: "Semua Topik",
      academic: "Akademik",
      facilities: "Kemudahan",
      events: "Acara",
      financial: "Kewangan",
      general: "Umum",
    },
    starterPrompts: [
      {
        category: "academic",
        title: "Penangguhan Pengajian",
        prompt: "Bagaimanakah cara memohon penangguhan pengajian atas sebab kesihatan?",
      },
      {
        category: "facilities",
        title: "Waktu Operasi Perpustakaan",
        prompt: "Apakah waktu operasi perpustakaan utama universiti?",
      },
      {
        category: "academic",
        title: "Tambah / Gugur Kursus",
        prompt: "Bilakah tempoh pendaftaran tambah dan gugur kursus dibuka?",
      },
      {
        category: "facilities",
        title: "Permohonan Asrama",
        prompt: "Siapakah yang layak memohon bilik kolej kediaman asrama?",
      },
    ],
    feedbackHelpful: "Jawapan membantu",
    feedbackNotHelpful: "Perlu penambahbaikan",
  },
};

