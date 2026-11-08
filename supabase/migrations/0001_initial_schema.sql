-- =============================================================================
-- UniVerse: Initial PostgreSQL Schema & Row Level Security (Supabase)
-- Migration: 0001_initial_schema.sql
-- =============================================================================

-- Enable required extensions
create extension if not exists "pgcrypto";

-- =============================================================================
-- 1. TABLES
-- =============================================================================

-- 1.1 Profiles Table (Synced with auth.users)
create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    email text not null,
    display_name text,
    role text not null default 'student' check (role in ('student', 'admin')),
    preferred_language text not null default 'en' check (preferred_language in ('en', 'ms')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- 1.2 Chat Sessions Table
create table if not exists public.chat_sessions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.profiles(id) on delete cascade,
    title text not null default 'New Conversation',
    language text not null default 'en' check (language in ('en', 'ms')),
    category_filter text not null default 'all' check (category_filter in ('academic', 'facilities', 'events', 'financial', 'general', 'all')),
    is_archived boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- 1.3 Chat Messages Table
create table if not exists public.messages (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references public.chat_sessions(id) on delete cascade,
    role text not null check (role in ('user', 'assistant')),
    content text not null,
    detected_language text not null default 'en' check (detected_language in ('en', 'ms')),
    citations jsonb not null default '[]'::jsonb,
    feedback_rating smallint check (feedback_rating in (-1, 1)),
    feedback_comment text,
    latency_ms integer,
    created_at timestamptz not null default now()
);

-- 1.4 Knowledge Base Documents Table
create table if not exists public.documents (
    id uuid primary key default gen_random_uuid(),
    title text not null,
    filename text not null,
    file_hash text not null unique,
    storage_path text not null,
    category text not null check (category in ('academic', 'facilities', 'events', 'financial', 'general')),
    language text not null default 'en' check (language in ('en', 'ms', 'bilingual')),
    status text not null default 'queued' check (status in ('queued', 'processing', 'indexed', 'failed')),
    error_message text,
    page_count integer not null default 0,
    chunk_count integer not null default 0,
    file_size_bytes bigint not null check (file_size_bytes > 0),
    uploaded_by uuid references public.profiles(id) on delete set null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- 1.5 RAG Evaluation Runs Table
create table if not exists public.eval_runs (
    id uuid primary key default gen_random_uuid(),
    triggered_by uuid references public.profiles(id) on delete set null,
    total_questions integer not null check (total_questions >= 0),
    avg_faithfulness numeric(5, 4) not null default 0,
    avg_answer_relevance numeric(5, 4) not null default 0,
    avg_context_recall numeric(5, 4) not null default 0,
    avg_citation_accuracy numeric(5, 4) not null default 0,
    case_results jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

-- =============================================================================
-- 2. INDEXES (Performance & Foreign Key Lookup Optimization)
-- =============================================================================

create index if not exists idx_chat_sessions_user_updated
    on public.chat_sessions (user_id, is_archived, updated_at desc);

create index if not exists idx_messages_session_created
    on public.messages (session_id, created_at asc);

create index if not exists idx_documents_active_status_category
    on public.documents (is_active, status, category, created_at desc);

create index if not exists idx_documents_uploaded_by
    on public.documents (uploaded_by);

create index if not exists idx_eval_runs_triggered_by_created
    on public.eval_runs (triggered_by, created_at desc);

-- =============================================================================
-- 3. TRIGGERS (Auto-timestamps & Auth User Sync)
-- =============================================================================

create or replace function public.handle_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists set_profiles_updated_at on public.profiles;
create trigger set_profiles_updated_at
    before update on public.profiles
    for each row execute function public.handle_updated_at();

drop trigger if exists set_chat_sessions_updated_at on public.chat_sessions;
create trigger set_chat_sessions_updated_at
    before update on public.chat_sessions
    for each row execute function public.handle_updated_at();

drop trigger if exists set_documents_updated_at on public.documents;
create trigger set_documents_updated_at
    before update on public.documents
    for each row execute function public.handle_updated_at();

-- Trigger function to automatically create a profile when a new Supabase user signs up
create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    insert into public.profiles (id, email, display_name, role, preferred_language)
    values (
        new.id,
        coalesce(new.email, ''),
        coalesce(new.raw_user_meta_data ->> 'display_name', split_part(coalesce(new.email, 'Student'), '@', 1)),
        case
            when (new.raw_app_meta_data ->> 'role') = 'admin' then 'admin'
            else 'student'
        end,
        case
            when (new.raw_user_meta_data ->> 'preferred_language') in ('en', 'ms')
                then (new.raw_user_meta_data ->> 'preferred_language')
            else 'en'
        end
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

-- Restrict execution on SECURITY DEFINER trigger function
revoke all on function public.handle_new_auth_user() from public, anon, authenticated;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_auth_user();

-- =============================================================================
-- 4. ROW LEVEL SECURITY (RLS) POLICIES
-- =============================================================================

alter table public.profiles enable row level security;
alter table public.chat_sessions enable row level security;
alter table public.messages enable row level security;
alter table public.documents enable row level security;
alter table public.eval_runs enable row level security;

-- Helper check: is current authenticated user an admin in profiles?
-- Uses SECURITY INVOKER and indexed PK lookup on profiles.id
create or replace function public.is_admin()
returns boolean
language sql
stable
security invoker
set search_path = ''
as $$
    select exists (
        select 1
        from public.profiles
        where id = (select auth.uid())
          and role = 'admin'
    );
$$;

-- 4.1 Profiles Policies
create policy "profiles_select_own_or_admin"
    on public.profiles for select
    to authenticated
    using ((select auth.uid()) = id or public.is_admin());

create policy "profiles_insert_own"
    on public.profiles for insert
    to authenticated
    with check ((select auth.uid()) = id and role = 'student');

create policy "profiles_update_own"
    on public.profiles for update
    to authenticated
    using ((select auth.uid()) = id)
    with check (
        (select auth.uid()) = id
        and role = (select p.role from public.profiles p where p.id = (select auth.uid()))
    );

-- 4.2 Chat Sessions Policies
create policy "chat_sessions_select_own"
    on public.chat_sessions for select
    to authenticated
    using ((select auth.uid()) = user_id);

create policy "chat_sessions_insert_own"
    on public.chat_sessions for insert
    to authenticated
    with check ((select auth.uid()) = user_id);

create policy "chat_sessions_update_own"
    on public.chat_sessions for update
    to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

create policy "chat_sessions_delete_own"
    on public.chat_sessions for delete
    to authenticated
    using ((select auth.uid()) = user_id);

-- 4.3 Messages Policies
create policy "messages_select_own_session"
    on public.messages for select
    to authenticated
    using (
        exists (
            select 1 from public.chat_sessions cs
            where cs.id = messages.session_id
              and cs.user_id = (select auth.uid())
        )
    );

create policy "messages_insert_own_session"
    on public.messages for insert
    to authenticated
    with check (
        exists (
            select 1 from public.chat_sessions cs
            where cs.id = messages.session_id
              and cs.user_id = (select auth.uid())
        )
    );

create policy "messages_update_feedback_own_session"
    on public.messages for update
    to authenticated
    using (
        exists (
            select 1 from public.chat_sessions cs
            where cs.id = messages.session_id
              and cs.user_id = (select auth.uid())
        )
    )
    with check (
        exists (
            select 1 from public.chat_sessions cs
            where cs.id = messages.session_id
              and cs.user_id = (select auth.uid())
        )
    );

-- 4.4 Documents Policies
create policy "documents_select_active_or_admin"
    on public.documents for select
    to authenticated
    using ((is_active = true and status = 'indexed') or public.is_admin());

create policy "documents_insert_admin_only"
    on public.documents for insert
    to authenticated
    with check (public.is_admin());

create policy "documents_update_admin_only"
    on public.documents for update
    to authenticated
    using (public.is_admin())
    with check (public.is_admin());

create policy "documents_delete_admin_only"
    on public.documents for delete
    to authenticated
    using (public.is_admin());

-- 4.5 Eval Runs Policies
create policy "eval_runs_select_admin_only"
    on public.eval_runs for select
    to authenticated
    using (public.is_admin());

create policy "eval_runs_insert_admin_only"
    on public.eval_runs for insert
    to authenticated
    with check (public.is_admin());

