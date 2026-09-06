create function public.set_artist_album_visibility(target_artist_id bigint, album_ids bigint[], make_public boolean, include_tracks boolean default false)
returns integer language plpgsql security invoker set search_path = '' as $$
declare changed integer;
begin
  if not coalesce(public.is_admin(),false) then raise exception '관리자 권한이 필요합니다.' using errcode='42501'; end if;
  if make_public is null or coalesce(cardinality(album_ids),0) = 0 then raise exception '앨범을 선택하세요.'; end if;
  perform id from public.artist_albums where artist_id=target_artist_id and id=any(album_ids) for update;
  if (select count(*) from public.artist_albums where artist_id=target_artist_id and id=any(album_ids)) <> (select count(distinct x) from unnest(album_ids) x) then raise exception '앨범이 삭제되었거나 다른 아티스트의 앨범입니다.'; end if;
  update public.artist_albums set active=make_public,updated_at=now() where artist_id=target_artist_id and id=any(album_ids);
  get diagnostics changed=row_count;
  if include_tracks then update public.artist_album_tracks set active=make_public,updated_at=now() where album_id=any(album_ids); end if;
  return changed;
end $$;
revoke all on function public.set_artist_album_visibility(bigint,bigint[],boolean,boolean) from public,anon;
grant execute on function public.set_artist_album_visibility(bigint,bigint[],boolean,boolean) to authenticated;
