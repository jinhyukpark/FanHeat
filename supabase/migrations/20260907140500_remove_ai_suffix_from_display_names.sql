-- AI identity is represented by profiles.is_ai and the profile badge, not a name suffix.
update public.ai_personas persona
set display_name = regexp_replace(persona.display_name, '[[:space:]]*AI$', '', 'i'),
    updated_at = now()
where persona.display_name ~* '[[:space:]]*AI$';

update public.profiles profile
set display_name = regexp_replace(profile.display_name, '[[:space:]]*AI$', '', 'i'),
    updated_at = now()
where profile.is_ai = true
  and profile.display_name ~* '[[:space:]]*AI$';

update auth.users account
set raw_user_meta_data = jsonb_set(
      coalesce(account.raw_user_meta_data, '{}'::jsonb),
      '{display_name}',
      to_jsonb(profile.display_name),
      true
    ),
    updated_at = now()
from public.profiles profile
where profile.id = account.id
  and profile.is_ai = true;

update public.posts post
set author_display_name = profile.display_name,
    updated_at = now()
from public.profiles profile
where profile.id = post.author_id
  and profile.is_ai = true
  and post.author_display_name is distinct from profile.display_name;

update public.comments comment
set author_display_name = profile.display_name,
    updated_at = now()
from public.profiles profile
where profile.id = comment.author_id
  and profile.is_ai = true
  and comment.author_display_name is distinct from profile.display_name;

update public.fan_photo_submissions submission
set submitter_name = profile.display_name,
    updated_at = now()
from public.profiles profile
where profile.id = submission.submitter_id
  and profile.is_ai = true
  and submission.submitter_name is distinct from profile.display_name;
