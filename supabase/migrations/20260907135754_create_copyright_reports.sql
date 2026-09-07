create table public.copyright_reports (
  id uuid primary key default gen_random_uuid(),
  reporter_id uuid not null references auth.users(id) on delete cascade,
  reporter_email text not null check (char_length(reporter_email) between 3 and 254),
  contact text not null check (char_length(contact) between 2 and 120),
  report_type text not null check (report_type in ('unauthorized_use', 'ownership', 'license', 'impersonation', 'other')),
  severity text not null default 'normal' check (severity in ('low', 'normal', 'high', 'urgent')),
  content text not null check (char_length(content) between 20 and 5000),
  status text not null default 'pending' check (status in ('pending', 'reviewing', 'resolved', 'rejected')),
  admin_note text not null default '' check (char_length(admin_note) <= 5000),
  reviewed_by uuid references auth.users(id) on delete set null,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index copyright_reports_status_created_idx
  on public.copyright_reports(status, created_at desc);

alter table public.copyright_reports enable row level security;

create policy copyright_reports_submit_own
  on public.copyright_reports for insert to authenticated
  with check (
    reporter_id = (select auth.uid())
    and status = 'pending'
    and admin_note = ''
    and reviewed_by is null
    and reviewed_at is null
  );

create policy copyright_reports_read_own_or_admin
  on public.copyright_reports for select to authenticated
  using (reporter_id = (select auth.uid()) or (select public.is_admin()));

create policy copyright_reports_admin_update
  on public.copyright_reports for update to authenticated
  using ((select public.is_admin()))
  with check (
    (select public.is_admin())
    and reviewed_by = (select auth.uid())
  );
