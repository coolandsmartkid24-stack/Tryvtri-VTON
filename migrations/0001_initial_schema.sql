-- =============================================================================
-- TryVtri — FASHN VTON 1.5 — initial schema
-- =============================================================================
-- Idempotent: every object is created with IF NOT EXISTS so this file can be
-- re-run safely.  Nothing here drops or alters an existing table.
--
-- Apply with:  python backend/scripts/apply_migrations.py
-- or paste into the Supabase SQL editor.
-- =============================================================================

-- ---------------------------------------------------------------- extensions
create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- customers --
create table if not exists public.customers (
    id                   uuid primary key default gen_random_uuid(),
    identity_key         text        not null unique,
    identity_type        text        not null
        check (identity_type in ('shopify', 'email', 'session')),
    shopify_customer_id  text,
    email                text,
    email_verified       boolean     not null default false,
    session_id           text,
    created_at           timestamptz not null default now(),
    last_activity_at     timestamptz not null default now()
);

create index if not exists customers_shopify_customer_id_idx
    on public.customers (shopify_customer_id)
    where shopify_customer_id is not null;
create index if not exists customers_email_idx
    on public.customers (lower(email))
    where email is not null;
create index if not exists customers_last_activity_idx
    on public.customers (last_activity_at desc);

comment on table public.customers is
    'Storefront visitors keyed by the strongest identity available: Shopify customer id, else email, else browser session id.';

-- ------------------------------------------------------------ try-on usage --
create table if not exists public.tryon_usage (
    id                 uuid primary key default gen_random_uuid(),
    request_id         text        not null unique,
    idempotency_key    text,
    customer_id        uuid        not null
        references public.customers (id) on delete cascade,
    product_id         text,
    variant_id         text,
    product_title      text,
    garment_category   text,
    garment_url        text,
    status             text        not null default 'pending'
        check (status in ('pending', 'success', 'failed')),
    error_code         text,
    error_message      text,
    duration_ms        integer,
    result_ref         text,
    created_at         timestamptz not null default now(),
    finished_at        timestamptz
);

create index if not exists tryon_usage_customer_status_idx
    on public.tryon_usage (customer_id, status, created_at desc);
create index if not exists tryon_usage_created_idx
    on public.tryon_usage (created_at desc);
create index if not exists tryon_usage_product_idx
    on public.tryon_usage (product_id, created_at desc)
    where product_id is not null;
create index if not exists tryon_usage_status_created_idx
    on public.tryon_usage (status, created_at desc);
create unique index if not exists tryon_usage_idempotency_idx
    on public.tryon_usage (idempotency_key)
    where idempotency_key is not null;

comment on table public.tryon_usage is
    'One row per try-on attempt. status=pending is an in-flight reservation, '
    'success consumes a free try, failed never does.';

-- -------------------------------------------------------------- gpu usage --
create table if not exists public.gpu_usage (
    id                  uuid primary key default gen_random_uuid(),
    provider            text        not null default 'lium',
    pod_id              text,
    pod_name            text,
    gpu_model           text,
    price_per_hour      numeric(10, 4),
    status              text        not null
        check (status in ('starting', 'running', 'stopping', 'stopped', 'error')),
    started_at          timestamptz,
    stopped_at          timestamptz,
    runtime_seconds     integer,
    estimated_cost_usd  numeric(12, 6) not null default 0,
    reported_spend_usd  numeric(12, 6),
    error_message       text,
    created_at          timestamptz not null default now()
);

create index if not exists gpu_usage_created_idx on public.gpu_usage (created_at desc);
create index if not exists gpu_usage_pod_idx on public.gpu_usage (pod_id)
    where pod_id is not null;
create index if not exists gpu_usage_status_idx on public.gpu_usage (status);

-- ------------------------------------------------------------- admin users --
create table if not exists public.admin_users (
    id             uuid primary key default gen_random_uuid(),
    username       text        not null unique,
    password_hash  text        not null,
    role           text        not null default 'admin'
        check (role in ('admin', 'owner', 'viewer')),
    created_at     timestamptz not null default now(),
    last_login_at  timestamptz
);

-- ----------------------------------------------------------- idempotency ---
create table if not exists public.api_idempotency (
    key           text primary key,
    request_id    text        not null,
    response_json jsonb,
    status_code   integer,
    created_at    timestamptz not null default now(),
    expires_at    timestamptz not null default now() + interval '24 hours'
);

create index if not exists api_idempotency_expires_idx
    on public.api_idempotency (expires_at);

-- =============================================================================
-- Row Level Security
-- =============================================================================
-- The anon/publishable key must not read any table.  The backend talks to
-- Supabase with the secret (service-role) key, which bypasses RLS.  Enabling
-- RLS with zero policies therefore locks every table for browser clients.
-- =============================================================================
alter table public.customers      enable row level security;
alter table public.tryon_usage    enable row level security;
alter table public.gpu_usage      enable row level security;
alter table public.admin_users    enable row level security;
alter table public.api_idempotency enable row level security;

-- Explicitly revoke the default "authenticated" role so a future policy is a
-- deliberate decision rather than an accident.
revoke all on table public.customers       from anon, authenticated;
revoke all on table public.tryon_usage     from anon, authenticated;
revoke all on table public.gpu_usage       from anon, authenticated;
revoke all on table public.admin_users     from anon, authenticated;
revoke all on table public.api_idempotency from anon, authenticated;
