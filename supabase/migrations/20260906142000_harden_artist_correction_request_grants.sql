-- Supabase projects created with legacy default grants can expose table-level
-- privileges to anon even when RLS has no anon policy. Keep the API surface
-- explicit: signed-in users may submit/read their requests, and only the
-- existing admin RLS policy permits review updates.
revoke all on public.artist_correction_requests from anon, authenticated;
grant select, insert on public.artist_correction_requests to authenticated;
grant update (status, admin_note, reviewed_at, reviewed_by)
  on public.artist_correction_requests to authenticated;
