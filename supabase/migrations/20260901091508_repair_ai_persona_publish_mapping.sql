-- Draft publication requires an enabled persona backed by a real AI profile.
-- Reassign unpublished drafts created by the original unprovisioned personas,
-- then prevent those personas from being selected again.
update public.ai_content_drafts d
set persona_id = (
      select replacement.id
      from public.ai_personas replacement
      join public.profiles profile
        on profile.id = replacement.profile_id
       and profile.is_ai = true
      where replacement.enabled = true
        and replacement.profile_id is not null
      order by md5(d.id::text || replacement.id::text)
      limit 1
    ),
    updated_at = now()
where d.status <> 'published'
  and exists (
    select 1
    from public.ai_personas current_persona
    left join public.profiles current_profile
      on current_profile.id = current_persona.profile_id
    where current_persona.id = d.persona_id
      and (current_persona.profile_id is null or coalesce(current_profile.is_ai, false) = false)
  )
  and exists (
    select 1
    from public.ai_personas replacement
    join public.profiles profile
      on profile.id = replacement.profile_id
     and profile.is_ai = true
    where replacement.enabled = true
      and replacement.profile_id is not null
  );

update public.ai_personas persona
set enabled = false,
    updated_at = now()
where persona.enabled = true
  and (
    persona.profile_id is null
    or not exists (
      select 1
      from public.profiles profile
      where profile.id = persona.profile_id
        and profile.is_ai = true
    )
  );
