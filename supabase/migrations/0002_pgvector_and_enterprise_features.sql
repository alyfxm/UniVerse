-- =============================================================================
-- UniVerse: Enterprise Evolution Migration (Supabase pgvector + Hybrid Search + SIS)
-- Migration: 0002_pgvector_and_enterprise_features.sql
-- =============================================================================

-- 1. Enable pgvector extension for native HNSW vector similarity inside PostgreSQL
create extension if not exists "vector";

-- 2. Unified Document Chunks Table (Replaces dual-store drift with ON DELETE CASCADE)
create table if not exists public.document_chunks (
    id text primary key,
    document_id uuid not null references public.documents(id) on delete cascade,
    document_title text not null,
    category text not null check (category in ('academic', 'facilities', 'events', 'financial', 'general')),
    language text not null default 'en' check (language in ('en', 'ms', 'bilingual')),
    page_number integer not null check (page_number >= 1),
    chunk_index integer not null check (chunk_index >= 0),
    content text not null,
    fts tsvector generated always as (to_tsvector('simple', coalesce(document_title, '') || ' ' || coalesce(content, ''))) stored,
    embedding vector(768),
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

-- Indexes for Hybrid Search (HNSW Vector + GIN Full-Text Search + Metadata Filter)
create index if not exists idx_document_chunks_embedding_hnsw
    on public.document_chunks using hnsw (embedding vector_cosine_ops);

create index if not exists idx_document_chunks_fts_gin
    on public.document_chunks using gin (fts);

create index if not exists idx_document_chunks_doc_active_cat
    on public.document_chunks (document_id, is_active, category);

-- RLS Policies for document_chunks
alter table public.document_chunks enable row level security;

create policy "document_chunks_select_active_or_admin"
    on public.document_chunks for select
    to authenticated
    using (is_active = true or public.is_admin());

create policy "document_chunks_write_admin_only"
    on public.document_chunks for all
    to authenticated
    using (public.is_admin())
    with check (public.is_admin());

-- 3. Hybrid Search RPC Function (Reciprocal Rank Fusion of pgvector + Full-Text Search)
create or replace function public.match_document_chunks_hybrid(
    query_text text,
    query_embedding vector(768),
    filter_category text default 'all',
    match_count int default 5,
    rrf_k int default 60
)
returns table (
    chunk_id text,
    document_id uuid,
    document_title text,
    category text,
    language text,
    page_number int,
    chunk_index int,
    content text,
    relevance_score float
)
language sql
stable
security invoker
set search_path = ''
as $$
    with dense_hits as (
        select
            dc.id,
            1.0 - (dc.embedding <=> query_embedding) as dense_sim,
            row_number() over (order by dc.embedding <=> query_embedding) as dense_rank
        from public.document_chunks dc
        where dc.is_active = true
          and (filter_category = 'all' or dc.category = filter_category)
        order by dc.embedding <=> query_embedding
        limit match_count * 4
    ),
    lexical_hits as (
        select
            dc.id,
            ts_rank_cd(dc.fts, websearch_to_tsquery('simple', query_text)) as lex_score,
            row_number() over (order by ts_rank_cd(dc.fts, websearch_to_tsquery('simple', query_text)) desc) as lex_rank
        from public.document_chunks dc
        where dc.is_active = true
          and (filter_category = 'all' or dc.category = filter_category)
          and dc.fts @@ websearch_to_tsquery('simple', query_text)
        order by lex_score desc
        limit match_count * 4
    ),
    fused as (
        select
            coalesce(d.id, l.id) as id,
            coalesce(1.0 / (rrf_k + d.dense_rank), 0.0) + coalesce(1.0 / (rrf_k + l.lex_rank), 0.0) as rrf_score,
            coalesce(d.dense_sim, 0.5) as dense_sim
        from dense_hits d
        full outer join lexical_hits l on d.id = l.id
    )
    select
        dc.id as chunk_id,
        dc.document_id,
        dc.document_title,
        dc.category,
        dc.language,
        dc.page_number,
        dc.chunk_index,
        dc.content,
        least(0.99, (0.7 * f.dense_sim) + (f.rrf_score * 3.0))::float as relevance_score
    from fused f
    join public.document_chunks dc on dc.id = f.id
    order by f.rrf_score desc
    limit match_count;
$$;

-- 4. Student Information System (SIS) Academic Context & Advisor Appointments
create table if not exists public.student_sis_profiles (
    user_id uuid primary key references public.profiles(id) on delete cascade,
    matric_number text not null unique,
    faculty text not null,
    program text not null,
    study_year integer not null check (study_year between 1 and 6),
    semester integer not null check (semester in (1, 2, 3)),
    cgpa numeric(3, 2) not null default 0.00,
    completed_courses text[] not null default '{}',
    academic_advisor text not null,
    scholarship_status text not null default 'Active',
    updated_at timestamptz not null default now()
);

alter table public.student_sis_profiles enable row level security;

create policy "student_sis_select_own_or_admin"
    on public.student_sis_profiles for select
    to authenticated
    using ((select auth.uid()) = user_id or public.is_admin());

create table if not exists public.advisor_appointments (
    id uuid primary key default gen_random_uuid(),
    student_id uuid not null references public.profiles(id) on delete cascade,
    advisor_name text not null,
    topic text not null,
    preferred_slot text not null,
    status text not null default 'confirmed' check (status in ('confirmed', 'cancelled')),
    created_at timestamptz not null default now()
);

alter table public.advisor_appointments enable row level security;

create policy "advisor_appointments_own_or_admin"
    on public.advisor_appointments for all
    to authenticated
    using ((select auth.uid()) = student_id or public.is_admin())
    with check ((select auth.uid()) = student_id or public.is_admin());

