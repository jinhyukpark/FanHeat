-- Auditable daily AI decisions for incoming friend requests.
-- Requests remain pending when deferred and may be reconsidered on a later day.

create table public.ai_friend_request_decisions (
  requester_id uuid not null references public.profiles(id) on delete cascade,
  ai_profile_id uuid not null references public.profiles(id) on delete cascade,
  persona_id uuid not null references public.ai_personas(id) on delete cascade,
  decision_date date not null,
  decision text not null check (decision in ('accepted', 'deferred')),
  probability numeric(5, 4) not null check (probability between 0 and 1),
  decision_context jsonb not null default '{}'::jsonb
    check (jsonb_typeof(decision_context) = 'object'),
  created_at timestamptz not null default now(),
  primary key (requester_id, ai_profile_id, decision_date),
  constraint ai_friend_request_not_self check (requester_id <> ai_profile_id)
);

create index ai_friend_request_decisions_ai_date_idx
  on public.ai_friend_request_decisions (ai_profile_id, decision_date desc);

alter table public.ai_friend_request_decisions enable row level security;
revoke all on public.ai_friend_request_decisions from public, anon, authenticated;
grant all on public.ai_friend_request_decisions to service_role;

comment on table public.ai_friend_request_decisions is
  'Backend-only audit log of persona-dependent AI decisions for incoming friend requests invoked by n8n.';
