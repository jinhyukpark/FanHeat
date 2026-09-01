-- The featured carousel is intentionally limited to five images in every client.
-- Enforce the same CMS rule in the database so direct API writes cannot bypass it.
create or replace function public.enforce_post_featured_image_limit()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    if (select count(*) from public.post_images where post_id = new.post_id) >= 5 then
      raise exception 'A post can have at most 5 featured images.'
        using errcode = '23514';
    end if;
  elsif new.post_id is distinct from old.post_id then
    if (select count(*) from public.post_images where post_id = new.post_id) >= 5 then
      raise exception 'A post can have at most 5 featured images.'
        using errcode = '23514';
    end if;
  end if;
  return new;
end;
$$;

revoke all on function public.enforce_post_featured_image_limit() from public;

drop trigger if exists enforce_post_featured_image_limit on public.post_images;
create trigger enforce_post_featured_image_limit
before insert or update of post_id on public.post_images
for each row execute function public.enforce_post_featured_image_limit();
