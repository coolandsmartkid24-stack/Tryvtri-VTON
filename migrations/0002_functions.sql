-- =============================================================================
-- TryVtri — database functions (atomic quota, identity, analytics)
-- =============================================================================
-- Everything that must be race-free lives here: the free-try reservation is a
-- single transaction that takes a row lock on the customer, so two parallel
-- requests can never both slip past the limit.
--
-- Idempotent: CREATE OR REPLACE everywhere.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Identity resolution -------------------------------------------------------
-- Priority is Shopify customer id > email > browser session.  When a visitor
-- who started anonymously later supplies an email or a Shopify id, the session
-- row is *adopted* so their existing usage carries over instead of resetting.
-- ---------------------------------------------------------------------------
create or replace function public.tryvtri_resolve_customer(
    p_identity_key      text,
    p_identity_type     text,
    p_shopify_customer_id text default null,
    p_email             text default null,
    p_session_id        text default null,
    p_email_verified    boolean default false
) returns public.customers
language plpgsql
security definer
set search_path = public
as $$
declare
    v_row public.customers;
begin
    if p_identity_key is null or p_identity_key = '' then
        raise exception 'identity_key is required';
    end if;
    if p_identity_type not in ('shopify', 'email', 'session') then
        raise exception 'invalid identity_type %', p_identity_type;
    end if;

    -- 1) already-known strong identity?
    select * into v_row from customers where identity_key = p_identity_key;

    if found then
        update customers
           set last_activity_at       = now(),
               email                  = coalesce(p_email, email),
               shopify_customer_id    = coalesce(p_shopify_customer_id, shopify_customer_id),
               email_verified         = email_verified or p_email_verified,
               session_id             = coalesce(p_session_id, session_id)
         where id = v_row.id
        returning * into v_row;
        return v_row;
    end if;

    -- 2) an anonymous session row that should be upgraded?
    if p_session_id is not null and p_session_id <> '' then
        select * into v_row from customers
         where session_id = p_session_id
         order by created_at
         limit 1;

        if found and v_row.identity_key <> p_identity_key then
            begin
                update customers
                   set identity_key         = p_identity_key,
                       identity_type        = p_identity_type,
                       shopify_customer_id  = coalesce(p_shopify_customer_id, shopify_customer_id),
                       email                = coalesce(p_email, email),
                       email_verified       = email_verified or p_email_verified,
                       session_id           = coalesce(p_session_id, session_id),
                       last_activity_at     = now()
                 where id = v_row.id
                returning * into v_row;
                return v_row;
            exception when unique_violation then
                -- the target key already belongs to somebody else; fall through
                null;
            end;
        end if;
    end if;

    -- 3) brand new identity
    begin
        insert into customers (
            identity_key, identity_type, shopify_customer_id,
            email, email_verified, session_id
        ) values (
            p_identity_key, p_identity_type, p_shopify_customer_id,
            p_email, p_email_verified, p_session_id
        )
        returning * into v_row;
    exception when unique_violation then
        select * into v_row from customers where identity_key = p_identity_key;
    end;

    return v_row;
end;
$$;

revoke all on function public.tryvtri_resolve_customer(text, text, text, text, text, boolean) from public;
grant execute on function public.tryvtri_resolve_customer(text, text, text, text, text, boolean) to service_role;

-- ---------------------------------------------------------------------------
-- Usage snapshot (read-only) ------------------------------------------------
-- ---------------------------------------------------------------------------
create or replace function public.tryvtri_get_usage(
    p_customer_id   uuid,
    p_window_hours  int default 24,
    p_limit         int default 2
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_used      int;
    v_pending   int;
    v_reset     timestamptz;
    v_limit     int := greatest(coalesce(p_limit, 2), 1);
    v_window    int := greatest(coalesce(p_window_hours, 24), 1);
begin
    select count(*) into v_used
      from tryon_usage
     where customer_id = p_customer_id
       and status = 'success'
       and created_at >= now() - make_interval(hours => v_window);

    select count(*) into v_pending
      from tryon_usage
     where customer_id = p_customer_id
       and status = 'pending'
       and created_at >= now() - interval '15 minutes';

    select min(created_at) into v_reset
      from tryon_usage
     where customer_id = p_customer_id
       and status = 'success'
       and created_at >= now() - make_interval(hours => v_window);

    return jsonb_build_object(
        'customer_id',  p_customer_id,
        'limit',        v_limit,
        'window_hours', v_window,
        'used',         v_used,
        'remaining',    greatest(v_limit - v_used, 0),
        'in_flight',    v_pending,
        'eligible',     (v_used + v_pending) < v_limit,
        'reset_at',     case when v_used >= v_limit and v_reset is not null
                             then v_reset + make_interval(hours => v_window)
                             else null end
    );
end;
$$;

revoke all on function public.tryvtri_get_usage(uuid, int, int) from public;
grant execute on function public.tryvtri_get_usage(uuid, int, int) to service_role;

-- ---------------------------------------------------------------------------
-- Reserve a free try --------------------------------------------------------
-- Serialised by FOR UPDATE on the customer row.  A pending reservation counts
-- against the limit while it is in flight so two concurrent requests cannot
-- both succeed past the ceiling; it stops counting the moment it becomes
-- 'failed', and a reservation older than 15 minutes is expired here.
-- ---------------------------------------------------------------------------
create or replace function public.tryvtri_reserve_try_on(
    p_request_id       text,
    p_customer_id      uuid,
    p_idempotency_key  text default null,
    p_window_hours     int  default 24,
    p_limit            int  default 2,
    p_product_id       text default null,
    p_variant_id       text default null,
    p_product_title    text default null,
    p_garment_category text default null,
    p_garment_url      text default null
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_row       public.tryon_usage;
    v_used      int;
    v_pending   int;
    v_reset     timestamptz;
    v_limit     int := greatest(coalesce(p_limit, 2), 1);
    v_window    int := greatest(coalesce(p_window_hours, 24), 1);
begin
    if p_request_id is null or p_request_id = '' then
        raise exception 'request_id is required';
    end if;

    -- Serialise every reservation for this customer.
    perform 1 from customers where id = p_customer_id for update;

    -- Replay: this request already made a decision.
    select * into v_row from tryon_usage where request_id = p_request_id;
    if found then
        return jsonb_build_object(
            'allowed',   v_row.status <> 'failed',
            'duplicate', true,
            'status',    v_row.status,
            'usage_id',  v_row.id,
            'used',      (select count(*) from tryon_usage
                           where customer_id = p_customer_id and status = 'success'
                             and created_at >= now() - make_interval(hours => v_window)),
            'remaining', null,
            'reason',    null
        );
    end if;

    -- Expire abandoned reservations so a crashed worker cannot lock a customer out.
    update tryon_usage
       set status = 'failed',
           error_code = 'reservation_expired',
           error_message = 'Reservation timed out before inference completed.',
           finished_at = now()
     where customer_id = p_customer_id
       and status = 'pending'
       and created_at < now() - interval '15 minutes';

    select count(*) into v_used
      from tryon_usage
     where customer_id = p_customer_id
       and status = 'success'
       and created_at >= now() - make_interval(hours => v_window);

    select count(*) into v_pending
      from tryon_usage
     where customer_id = p_customer_id
       and status = 'pending'
       and created_at >= now() - interval '15 minutes';

    if v_used + v_pending >= v_limit then
        select min(created_at) into v_reset
          from tryon_usage
         where customer_id = p_customer_id
           and status = 'success'
           and created_at >= now() - make_interval(hours => v_window);

        return jsonb_build_object(
            'allowed',    false,
            'duplicate',  false,
            'status',     'denied',
            'usage_id',   null,
            'used',       v_used,
            'remaining',  greatest(v_limit - v_used, 0),
            'in_flight',  v_pending,
            'reset_at',   case when v_reset is not null
                               then v_reset + make_interval(hours => v_window)
                               else now() + make_interval(hours => v_window) end,
            'reason',     'quota_exceeded'
        );
    end if;

    insert into tryon_usage (
        request_id, idempotency_key, customer_id, product_id, variant_id,
        product_title, garment_category, garment_url, status
    ) values (
        p_request_id, p_idempotency_key, p_customer_id, p_product_id, p_variant_id,
        p_product_title, p_garment_category, p_garment_url, 'pending'
    )
    returning * into v_row;

    return jsonb_build_object(
        'allowed',    true,
        'duplicate',  false,
        'status',     'pending',
        'usage_id',   v_row.id,
        'used',       v_used,
        'remaining',  greatest(v_limit - v_used - 1, 0),
        'in_flight',  v_pending,
        'reset_at',   null,
        'reason',     null
    );
end;
$$;

revoke all on function public.tryvtri_reserve_try_on(text, uuid, text, int, int, text, text, text, text, text) from public;
grant execute on function public.tryvtri_reserve_try_on(text, uuid, text, int, int, text, text, text, text, text) to service_role;

-- ---------------------------------------------------------------------------
-- Finalise a reservation ----------------------------------------------------
-- Only a 'pending' row may transition, so a retry of the same request id can
-- never double-count, and a failure can never consume a free try.
-- ---------------------------------------------------------------------------
create or replace function public.tryvtri_finalize_try_on(
    p_request_id    text,
    p_status        text,
    p_error_code    text default null,
    p_error_message text default null,
    p_duration_ms   integer default null,
    p_result_ref    text default null
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_row   public.tryon_usage;
    v_usage jsonb;
begin
    if p_status not in ('success', 'failed') then
        raise exception 'invalid status %', p_status;
    end if;

    update tryon_usage
       set status        = p_status,
           error_code    = p_error_code,
           error_message = left(coalesce(p_error_message, ''), 1000),
           duration_ms   = p_duration_ms,
           result_ref    = p_result_ref,
           finished_at   = now()
     where request_id = p_request_id
       and status = 'pending'
    returning * into v_row;

    if not found then
        select * into v_row from tryon_usage where request_id = p_request_id;
        if not found then
            return jsonb_build_object('ok', false, 'reason', 'unknown_request');
        end if;
        return jsonb_build_object('ok', false, 'reason', 'already_finalised',
                                  'status', v_row.status, 'customer_id', v_row.customer_id);
    end if;

    v_usage := public.tryvtri_get_usage(v_row.customer_id, 24, 2);

    return jsonb_build_object(
        'ok',          true,
        'status',      v_row.status,
        'customer_id', v_row.customer_id,
        'used',        v_usage -> 'used',
        'remaining',   v_usage -> 'remaining',
        'reset_at',    v_usage -> 'reset_at'
    );
end;
$$;

revoke all on function public.tryvtri_finalize_try_on(text, text, text, text, integer, text) from public;
grant execute on function public.tryvtri_finalize_try_on(text, text, text, text, integer, text) to service_role;

-- ---------------------------------------------------------------------------
-- Admin analytics -----------------------------------------------------------
-- ---------------------------------------------------------------------------
create or replace function public.tryvtri_dashboard_stats(
    p_window_hours int default 24
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_total_customers        bigint;
    v_demo_customers         bigint;
    v_success                bigint;
    v_failed                 bigint;
    v_pending                bigint;
    v_consumed               bigint;
    v_exhausted              bigint;
    v_eligible               bigint;
    v_window_success         bigint;
    v_gpu_sessions           bigint;
    v_gpu_runtime            bigint;
    v_gpu_cost               numeric;
    v_window int := greatest(coalesce(p_window_hours, 24), 1);
begin
    select count(*) into v_total_customers from customers;

    select count(distinct customer_id) into v_demo_customers
      from tryon_usage where status = 'success';

    select count(*) filter (where status = 'success'),
           count(*) filter (where status = 'failed'),
           count(*) filter (where status = 'pending')
      into v_success, v_failed, v_pending
      from tryon_usage;

    v_consumed := v_success;

    -- customers whose rolling window is full
    select count(*) into v_exhausted
      from (
        select customer_id
          from tryon_usage
         where status = 'success'
           and created_at >= now() - make_interval(hours => v_window)
         group by customer_id
        having count(*) >= 2
      ) x;

    v_eligible := greatest(v_total_customers - v_exhausted, 0);

    select count(*) filter (where created_at >= now() - make_interval(hours => v_window))
      into v_window_success
      from tryon_usage where status = 'success';

    select count(*),
           coalesce(sum(runtime_seconds), 0),
           coalesce(sum(estimated_cost_usd), 0)
      into v_gpu_sessions, v_gpu_runtime, v_gpu_cost
      from gpu_usage;

    return jsonb_build_object(
        'total_customers',        v_total_customers,
        'demo_customers',         v_demo_customers,
        'successful_tryons',      v_success,
        'failed_tryons',          v_failed,
        'pending_tryons',         v_pending,
        'free_tries_consumed',    v_consumed,
        'exhausted_customers',    v_exhausted,
        'eligible_customers',     v_eligible,
        'success_last_window',    v_window_success,
        'window_hours',           v_window,
        'gpu_sessions',           v_gpu_sessions,
        'gpu_runtime_seconds',    v_gpu_runtime,
        'gpu_estimated_cost_usd', round(v_gpu_cost, 4)
    );
end;
$$;

revoke all on function public.tryvtri_dashboard_stats(int) from public;
grant execute on function public.tryvtri_dashboard_stats(int) to service_role;

create or replace function public.tryvtri_daily_usage(p_days int default 30)
returns table (
    day         date,
    total       bigint,
    success     bigint,
    failed      bigint
)
language sql
security definer
set search_path = public
stable
as $$
    select date_trunc('day', u.created_at)::date as day,
           count(*)                              as total,
           count(*) filter (where u.status = 'success') as success,
           count(*) filter (where u.status = 'failed')   as failed
      from tryon_usage u
     where u.created_at >= now() - make_interval(days => greatest(coalesce(p_days, 30), 1))
     group by 1
     order by 1;
$$;

revoke all on function public.tryvtri_daily_usage(int) from public;
grant execute on function public.tryvtri_daily_usage(int) to service_role;

create or replace function public.tryvtri_product_usage(p_days int default 30)
returns table (
    product_id    text,
    product_title text,
    total         bigint,
    success       bigint,
    failed        bigint
)
language sql
security definer
set search_path = public
stable
as $$
    select u.product_id,
           max(u.product_title) as product_title,
           count(*)             as total,
           count(*) filter (where u.status = 'success') as success,
           count(*) filter (where u.status = 'failed')   as failed
      from tryon_usage u
     where u.created_at >= now() - make_interval(days => greatest(coalesce(p_days, 30), 1))
       and u.product_id is not null
     group by u.product_id
     order by count(*) desc
     limit 50;
$$;

revoke all on function public.tryvtri_product_usage(int) from public;
grant execute on function public.tryvtri_product_usage(int) to service_role;

create or replace function public.tryvtri_customer_list(
    p_limit  int default 50,
    p_offset int default 0,
    p_search text default null,
    p_window_hours int default 24,
    p_limit_tries int default 2
) returns table (
    customer_id          uuid,
    identity_type        text,
    email                text,
    shopify_customer_id  text,
    email_verified       boolean,
    created_at           timestamptz,
    last_activity_at     timestamptz,
    successful_tryons    bigint,
    failed_tryons        bigint,
    remaining_tries      bigint,
    last_tryon_at        timestamptz,
    next_eligible_at     timestamptz,
    quota_exhausted      boolean
)
language sql
security definer
set search_path = public
stable
as $$
    with usage as (
        select u.customer_id,
               count(*) filter (where u.status = 'success') as ok,
               count(*) filter (where u.status = 'failed')  as bad,
               max(u.created_at) filter (where u.status = 'success') as last_ok,
               min(u.created_at) filter (where u.status = 'success'
                     and u.created_at >= now() - make_interval(hours => greatest(coalesce(p_window_hours,24),1))) as oldest_ok
          from tryon_usage u
         group by u.customer_id
    )
    select c.id,
           c.identity_type,
           c.email,
           c.shopify_customer_id,
           c.email_verified,
           c.created_at,
           c.last_activity_at,
           coalesce(u.ok, 0),
           coalesce(u.bad, 0),
           greatest(coalesce(p_limit_tries, 2) - coalesce(u.ok, 0), 0),
           u.last_ok,
           case
             when coalesce(u.ok, 0) >= greatest(coalesce(p_limit_tries,2),1) and u.oldest_ok is not null
               then u.oldest_ok + make_interval(hours => greatest(coalesce(p_window_hours,24),1))
             else null
           end,
           coalesce(u.ok, 0) >= greatest(coalesce(p_limit_tries,2),1)
      from customers c
      left join usage u on u.customer_id = c.id
     where p_search is null
        or p_search = ''
        or c.email ilike '%' || p_search || '%'
        or c.shopify_customer_id = p_search
        or c.identity_key ilike '%' || p_search || '%'
     order by c.last_activity_at desc
     limit greatest(coalesce(p_limit, 50), 1)
    offset greatest(coalesce(p_offset, 0), 0);
$$;

revoke all on function public.tryvtri_customer_list(int, int, text, int, int) from public;
grant execute on function public.tryvtri_customer_list(int, int, text, int, int) to service_role;

create or replace function public.tryvtri_recent_activity(p_limit int default 25)
returns table (
    request_id      text,
    customer_id     uuid,
    email           text,
    product_id      text,
    product_title   text,
    status          text,
    error_code      text,
    duration_ms     integer,
    created_at      timestamptz
)
language sql
security definer
set search_path = public
stable
as $$
    select u.request_id,
           u.customer_id,
           c.email,
           u.product_id,
           u.product_title,
           u.status,
           u.error_code,
           u.duration_ms,
           u.created_at
      from tryon_usage u
      left join customers c on c.id = u.customer_id
     order by u.created_at desc
     limit greatest(coalesce(p_limit, 25), 1);
$$;

revoke all on function public.tryvtri_recent_activity(int) from public;
grant execute on function public.tryvtri_recent_activity(int) to service_role;
