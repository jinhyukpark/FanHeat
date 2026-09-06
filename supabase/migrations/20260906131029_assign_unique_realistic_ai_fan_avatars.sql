-- Give each fictional AI fan a unique, photorealistic profile image.
with avatar_assignment(display_name, avatar_url) as (
  values
    ('하린AI', '/images/ai-profiles/realistic-v1/ai-fan-01.jpg'),
    ('서윤AI', '/images/ai-profiles/realistic-v1/ai-fan-02.jpg'),
    ('지우AI', '/images/ai-profiles/realistic-v1/ai-fan-03.jpg'),
    ('수아AI', '/images/ai-profiles/realistic-v1/ai-fan-04.jpg'),
    ('채원AI', '/images/ai-profiles/realistic-v1/ai-fan-05.jpg'),
    ('유나AI', '/images/ai-profiles/realistic-v1/ai-fan-06.jpg'),
    ('다은AI', '/images/ai-profiles/realistic-v1/ai-fan-07.jpg'),
    ('소민AI', '/images/ai-profiles/realistic-v1/ai-fan-08.jpg'),
    ('아린AI', '/images/ai-profiles/realistic-v1/ai-fan-09.jpg'),
    ('나연AI', '/images/ai-profiles/realistic-v1/ai-fan-10.jpg'),
    ('보민AI', '/images/ai-profiles/realistic-v1/ai-fan-11.jpg'),
    ('세아AI', '/images/ai-profiles/realistic-v1/ai-fan-12.jpg'),
    ('라희AI', '/images/ai-profiles/realistic-v1/ai-fan-13.jpg'),
    ('혜원AI', '/images/ai-profiles/realistic-v1/ai-fan-14.jpg'),
    ('은채AI', '/images/ai-profiles/realistic-v1/ai-fan-15.jpg'),
    ('가은AI', '/images/ai-profiles/realistic-v1/ai-fan-16.jpg'),
    ('연우AI', '/images/ai-profiles/realistic-v1/ai-fan-17.jpg'),
    ('미소AI', '/images/ai-profiles/realistic-v1/ai-fan-18.jpg'),
    ('서아AI', '/images/ai-profiles/realistic-v1/ai-fan-19.jpg'),
    ('유림AI', '/images/ai-profiles/realistic-v1/ai-fan-20.jpg'),
    ('해인AI', '/images/ai-profiles/realistic-v1/ai-fan-21.jpg'),
    ('예린AI', '/images/ai-profiles/realistic-v1/ai-fan-22.jpg'),
    ('로아AI', '/images/ai-profiles/realistic-v1/ai-fan-23.jpg'),
    ('소율AI', '/images/ai-profiles/realistic-v1/ai-fan-24.jpg'),
    ('다인AI', '/images/ai-profiles/realistic-v1/ai-fan-25.jpg'),
    ('민준AI', '/images/ai-profiles/realistic-v1/ai-fan-26.jpg'),
    ('도윤AI', '/images/ai-profiles/realistic-v1/ai-fan-27.jpg'),
    ('예준AI', '/images/ai-profiles/realistic-v1/ai-fan-28.jpg'),
    ('현우AI', '/images/ai-profiles/realistic-v1/ai-fan-29.jpg'),
    ('시우AI', '/images/ai-profiles/realistic-v1/ai-fan-30.jpg'),
    ('준서AI', '/images/ai-profiles/realistic-v1/ai-fan-31.jpg'),
    ('건우AI', '/images/ai-profiles/realistic-v1/ai-fan-32.jpg'),
    ('태윤AI', '/images/ai-profiles/realistic-v1/ai-fan-33.jpg'),
    ('재민AI', '/images/ai-profiles/realistic-v1/ai-fan-34.jpg'),
    ('성민AI', '/images/ai-profiles/realistic-v1/ai-fan-35.jpg'),
    ('우진AI', '/images/ai-profiles/realistic-v1/ai-fan-36.jpg'),
    ('정우AI', '/images/ai-profiles/realistic-v1/ai-fan-37.jpg'),
    ('승현AI', '/images/ai-profiles/realistic-v1/ai-fan-38.jpg'),
    ('진우AI', '/images/ai-profiles/realistic-v1/ai-fan-39.jpg'),
    ('태민AI', '/images/ai-profiles/realistic-v1/ai-fan-40.jpg'),
    ('동현AI', '/images/ai-profiles/realistic-v1/ai-fan-41.jpg'),
    ('하준AI', '/images/ai-profiles/realistic-v1/ai-fan-42.jpg'),
    ('윤호AI', '/images/ai-profiles/realistic-v1/ai-fan-43.jpg'),
    ('지한AI', '/images/ai-profiles/realistic-v1/ai-fan-44.jpg'),
    ('민재AI', '/images/ai-profiles/realistic-v1/ai-fan-45.jpg'),
    ('주원AI', '/images/ai-profiles/realistic-v1/ai-fan-46.jpg'),
    ('시현AI', '/images/ai-profiles/realistic-v1/ai-fan-47.jpg'),
    ('규민AI', '/images/ai-profiles/realistic-v1/ai-fan-48.jpg'),
    ('준영AI', '/images/ai-profiles/realistic-v1/ai-fan-49.jpg'),
    ('이든AI', '/images/ai-profiles/realistic-v1/ai-fan-50.jpg')
)
update public.profiles profile
set avatar_url = assignment.avatar_url,
    avatar_urls = array[assignment.avatar_url],
    updated_at = now()
from avatar_assignment assignment
where profile.is_ai = true
  and profile.display_name = assignment.display_name;

-- Existing AI comments denormalize profile imagery, so keep them in sync.
update public.comments comment_row
set author_avatar_url = profile.avatar_url,
    updated_at = now()
from public.profiles profile
where comment_row.author_id = profile.id
  and profile.is_ai = true
  and profile.avatar_url is not null;
