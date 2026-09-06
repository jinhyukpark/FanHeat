alter table public.artists add column review_pending boolean not null default false;
-- Preserve existing hidden records; only newly registered hidden artists default to review.
alter table public.artists alter column review_pending set default true;
create function public.normalize_artist_review_status() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
  if new.active then
    new.review_pending := false;
  elsif tg_op = 'UPDATE' then
    if old.active and not new.active then new.review_pending := false; end if;
  end if;
  return new;
end;
$$;
revoke all on function public.normalize_artist_review_status() from public, anon, authenticated;
create trigger normalize_artist_review_status before insert or update on public.artists
for each row execute function public.normalize_artist_review_status();
alter table public.artists add constraint artists_review_visibility check (not(active and review_pending));
