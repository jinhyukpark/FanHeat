-- AI profile covers are original FANHEAT assets generated for this project.
-- Keep avatar photos unchanged and replace only the large profile background.
with ranked_ai_profiles as (
  select
    profile.id,
    row_number() over (order by profile.id) - 1 as cover_index
  from public.profiles profile
  where profile.is_ai = true
), assigned_covers as (
  select
    ranked.id,
    (array[
      '/images/ai-profile-covers/moon-clouds.jpg',
      '/images/ai-profile-covers/aurora-lake.jpg',
      '/images/ai-profile-covers/prism-beach.jpg',
      '/images/ai-profile-covers/glow-forest.jpg',
      '/images/ai-profile-covers/neon-city.jpg',
      '/images/ai-profile-covers/liquid-pop.jpg'
    ]::text[])[1 + (ranked.cover_index % 6)] as cover_url
  from ranked_ai_profiles ranked
)
update public.profiles profile
set
  cover_url = assigned.cover_url,
  cover_urls = array[assigned.cover_url],
  cover_object_path = null,
  cover_object_paths = '{}'::text[],
  updated_at = now()
from assigned_covers assigned
where profile.id = assigned.id;
