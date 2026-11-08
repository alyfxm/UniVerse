# UniVerse — Multilingual AI Campus Assistant

UniVerse is a production-grade, multilingual (**Bahasa Melayu & English**) RAG campus assistant built with **Next.js 15 + TypeScript**, **Python + FastAPI**, **Google Gemini**, **Supabase (Auth, PostgreSQL & Storage)**, and **ChromaDB**.

## Core Capabilities
1. **Grounded RAG Question-Answering**: Answers student questions strictly using indexed university PDFs with automatic unanswerable query fallback.
2. **Page-Accurate PDF Ingestion Pipeline**: Extracts text per page (`PyMuPDF`), normalizes layout, chunks with sliding-window overlap, and preserves exact 1-based `page_number` metadata.
3. **Multilingual Semantic Search (Malay & English)**: Uses `gemini-embedding-001` with cross-lingual concept expansion in ChromaDB so students can ask in Bahasa Melayu and retrieve from English handbooks (or vice versa).
4. **Interactive Page Citations (`[1]`, `[2]`)**: Clicking any inline citation badge opens the slide-over **PDF Page Citation Drawer** anchored directly to `#page=N`.
5. **Supabase Auth, RBAC & Chat History**: Role-based access control (`student` vs `admin`), Row Level Security (RLS) policies in `supabase/migrations/0001_initial_schema.sql`, and multi-session chat history.
6. **Admin Knowledge Dashboard & RAG Evaluation Framework**: Upload/toggle/delete PDFs and run automated RAG evaluations measuring **Faithfulness**, **Answer Relevance**, **Context Recall**, and **Citation Accuracy** against `apps/api/eval/golden_dataset.json`.

---

## Project Structure

```text
UniVerse/
├── apps/
│   ├── api/                    # Python FastAPI Backend
│   │   ├── app/
│   │   │   ├── core/           # Config, structured logging, RFC 7807 errors, Supabase JWT security
│   │   │   ├── models/         # Pydantic v2 schemas (auth, documents, chat, eval)
│   │   │   ├── repositories/   # Supabase PostgreSQL, Storage, and ChromaDB repositories
│   │   │   ├── routers/        # API v1 endpoints (health, auth, documents, chat, search, eval)
│   │   │   └── services/       # PDF processor, embeddings, RAG engine, evaluation runner
│   │   ├── eval/               # Bilingual golden benchmark dataset (golden_dataset.json)
│   │   └── tests/              # Pytest unit & integration suites (Milestones 1–5)
│   └── web/                    # Next.js + TypeScript + Tailwind CSS Frontend
│       ├── src/
│       │   ├── app/            # App Router pages (/ and /admin)
│       │   ├── components/     # ChatInterface, MessageItem, CitationDrawer, AdminDashboard, Navbar
│       │   ├── context/        # AuthContext & LanguageContext (EN / MS)
│       │   ├── lib/            # Typed API client, Supabase SSR client, bilingual i18n dictionary
│       │   └── types/          # Shared TypeScript interfaces
│       └── tests/              # Vitest UI & integration tests
└── supabase/
    └── migrations/
        └── 0001_initial_schema.sql
```

---

## Quick Start

### 1. Backend API (`apps/api`)
```bash
cd apps/api
cp .env.example .env
# Activate virtual environment and start FastAPI server on port 8000
.venv/Scripts/uvicorn app.main:app --reload --port 8000
```

### 2. Frontend Web App (`apps/web`)
```bash
cd apps/web
cp .env.example .env.local
npm run dev
```
Open `http://localhost:3000` to use the Student Chat Assistant or `http://localhost:3000/admin` for the Admin Knowledge & Evaluation Dashboard.

### 3. Running Automated Tests
```bash
# Backend Unit & Integration Tests (Pytest)
apps/api/.venv/Scripts/pytest apps/api/tests -v

# Frontend Typecheck & Component Tests (Vitest)
npm --prefix apps/web run typecheck
npm --prefix apps/web test
```

