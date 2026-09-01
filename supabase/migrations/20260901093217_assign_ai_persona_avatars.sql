-- Assign illustrated, non-photorealistic avatars to the fictional AI personas.
-- These groups are presentation choices only; no gender attribute is persisted.
with avatar_assignment(display_name, avatar_url) as (
  values
    ('하린AI','/images/ai-profiles/female-1.png'), ('서윤AI','/images/ai-profiles/female-2.png'),
    ('지우AI','/images/ai-profiles/female-1.png'), ('수아AI','/images/ai-profiles/female-2.png'),
    ('채원AI','/images/ai-profiles/female-1.png'), ('유나AI','/images/ai-profiles/female-2.png'),
    ('다은AI','/images/ai-profiles/female-1.png'), ('소민AI','/images/ai-profiles/female-2.png'),
    ('아린AI','/images/ai-profiles/female-1.png'), ('나연AI','/images/ai-profiles/female-2.png'),
    ('보민AI','/images/ai-profiles/female-1.png'), ('세아AI','/images/ai-profiles/female-2.png'),
    ('라희AI','/images/ai-profiles/female-1.png'), ('혜원AI','/images/ai-profiles/female-2.png'),
    ('은채AI','/images/ai-profiles/female-1.png'), ('가은AI','/images/ai-profiles/female-2.png'),
    ('연우AI','/images/ai-profiles/female-1.png'), ('미소AI','/images/ai-profiles/female-2.png'),
    ('서아AI','/images/ai-profiles/female-1.png'), ('유림AI','/images/ai-profiles/female-2.png'),
    ('해인AI','/images/ai-profiles/female-1.png'), ('예린AI','/images/ai-profiles/female-2.png'),
    ('로아AI','/images/ai-profiles/female-1.png'), ('소율AI','/images/ai-profiles/female-2.png'),
    ('다인AI','/images/ai-profiles/female-1.png'),
    ('민준AI','/images/ai-profiles/male-1.png'), ('도윤AI','/images/ai-profiles/male-2.png'),
    ('예준AI','/images/ai-profiles/male-1.png'), ('현우AI','/images/ai-profiles/male-2.png'),
    ('시우AI','/images/ai-profiles/male-1.png'), ('준서AI','/images/ai-profiles/male-2.png'),
    ('건우AI','/images/ai-profiles/male-1.png'), ('태윤AI','/images/ai-profiles/male-2.png'),
    ('재민AI','/images/ai-profiles/male-1.png'), ('성민AI','/images/ai-profiles/male-2.png'),
    ('우진AI','/images/ai-profiles/male-1.png'), ('정우AI','/images/ai-profiles/male-2.png'),
    ('승현AI','/images/ai-profiles/male-1.png'), ('진우AI','/images/ai-profiles/male-2.png'),
    ('태민AI','/images/ai-profiles/male-1.png'), ('동현AI','/images/ai-profiles/male-2.png'),
    ('하준AI','/images/ai-profiles/male-1.png'), ('윤호AI','/images/ai-profiles/male-2.png'),
    ('지한AI','/images/ai-profiles/male-1.png'), ('민재AI','/images/ai-profiles/male-2.png'),
    ('주원AI','/images/ai-profiles/male-1.png'), ('시현AI','/images/ai-profiles/male-2.png'),
    ('규민AI','/images/ai-profiles/male-1.png'), ('준영AI','/images/ai-profiles/male-2.png'),
    ('이든AI','/images/ai-profiles/male-1.png')
)
update public.profiles profile
set avatar_url = assignment.avatar_url,
    avatar_urls = array[assignment.avatar_url],
    updated_at = now()
from avatar_assignment assignment
where profile.is_ai = true
  and profile.display_name = assignment.display_name;

-- Existing AI comments denormalize the avatar, so keep them in sync too.
update public.comments comment_row
set author_avatar_url = profile.avatar_url,
    updated_at = now()
from public.profiles profile
where comment_row.author_id = profile.id
  and profile.is_ai = true
  and profile.avatar_url is not null;
