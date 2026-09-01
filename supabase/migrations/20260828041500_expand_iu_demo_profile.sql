-- Rich IU profile fixtures for testing the introduction, history, and award UI.

update public.artists
set
  description = '아이유는 섬세한 감성과 폭넓은 음악적 스펙트럼으로 사랑받는 싱어송라이터이자 배우입니다.',
  bio_paragraphs = array[
    '아이유는 2008년 데뷔 이후 자신만의 감성과 서사를 음악으로 전해 온 싱어송라이터입니다.',
    '맑고 섬세한 음색부터 깊이 있는 표현력까지 폭넓은 음악적 스펙트럼을 보여주며 세대를 아우르는 사랑을 받고 있습니다.',
    '정규 앨범과 미니 앨범, 리메이크 프로젝트를 통해 다양한 장르를 자신만의 색으로 재해석해 왔습니다.',
    '작사와 작곡에도 꾸준히 참여하며 일상의 감정과 성장의 순간을 진솔한 언어로 담아내고 있습니다.',
    '배우로서도 드라마와 영화에서 다양한 캐릭터를 소화하며 음악과 연기를 넘나드는 활동을 이어가고 있습니다.',
    '팬덤 UAENA와 함께 공연, 기부, 팬 프로젝트 등 여러 활동을 지속하며 따뜻한 영향력을 전하고 있습니다.'
  ],
  history_items = jsonb_build_array(
    jsonb_build_object('year', '2026', 'text', 'FAN HEAT 아이유 아티스트 상세 페이지 및 갤러리 공개'),
    jsonb_build_object('year', '2025', 'text', '팬 프로젝트와 공연 콘텐츠를 중심으로 다양한 활동 진행'),
    jsonb_build_object('year', '2024', 'text', '새로운 음악과 콘서트를 통해 팬들과 만남'),
    jsonb_build_object('year', '2022', 'text', '단독 콘서트와 배우 활동을 함께 전개'),
    jsonb_build_object('year', '2021', 'text', '정규 앨범을 발표하며 싱어송라이터로서의 음악 세계 확장'),
    jsonb_build_object('year', '2017', 'text', '정규 앨범 Palette 발표 및 주요 음원 차트에서 활약'),
    jsonb_build_object('year', '2011', 'text', '정규 앨범 Last Fantasy 발표'),
    jsonb_build_object('year', '2008', 'text', '미니 앨범 Lost and Found로 데뷔')
  ),
  award_items = jsonb_build_array(
    jsonb_build_object('year', '2025', 'text', 'FAN HEAT 올해의 아티스트 선정'),
    jsonb_build_object('year', '2024', 'text', '글로벌 팬 초이스 솔로 아티스트 부문'),
    jsonb_build_object('year', '2023', 'text', '디지털 콘텐츠 인기상'),
    jsonb_build_object('year', '2022', 'text', '올해의 음원 및 팬 인기상'),
    jsonb_build_object('year', '2021', 'text', '올해의 아티스트 및 작사가 부문'),
    jsonb_build_object('year', '2019', 'text', '대중문화 인기 아티스트상'),
    jsonb_build_object('year', '2017', 'text', '올해의 앨범 및 베스트 솔로 아티스트상'),
    jsonb_build_object('year', '2015', 'text', '디지털 음원 본상'),
    jsonb_build_object('year', '2012', 'text', '최우수 여자 솔로 아티스트상'),
    jsonb_build_object('year', '2011', 'text', '올해의 노래 및 음원 대상')
  ),
  updated_at = now()
where slug = 'iu';
