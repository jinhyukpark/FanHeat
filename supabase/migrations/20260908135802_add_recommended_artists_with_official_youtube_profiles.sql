-- Public artist cards use the current thumbnail exposed by each verified
-- official YouTube channel. The image remains remote; FANHEAT does not copy or
-- claim ownership of it. Source metadata is retained for replacement/audit.
with official_artist(slug, name, name_ko, debut_text, channel_id, channel_url, thumbnail_url) as (
  values
    ('i-dle-q51885404','i-dle','아이들','2018','UCritGVo7pLJLUS8wEu32vow','https://www.youtube.com/@official_i_dle','https://yt3.ggpht.com/296qkNEuqGTgJt0cg0h4aotQl6rK-ssj0yCxw1w4VmJDVoRpg8uM_LfuWn_wC-ns1feetX6F=s800-c-k-c0x00ffffff-no-rj'),
    ('riize-q121075203','Riize','RIIZE','2023','UCdVD0MsYecQaIE5Ru-pOIQQ','https://www.youtube.com/@riize_official','https://yt3.ggpht.com/HonsPgcftnH9zgZRBanGOYB4fG_CH0GOoXOsmzkLcVfmA8a7D25fjT4RfeSfRjZYJt2R25RU=s800-c-k-c0x00ffffff-no-rj'),
    ('boynextdoor-q118178306','BOYNEXTDOOR','보이넥스트도어','2023','UChhKBlh_wvspTh5n4mL0b5g','https://www.youtube.com/@boynextdoor_official','https://yt3.ggpht.com/fHImL9mm_mmZMRpn9mKciWCnvxsQ5_enwggEso4cM-DSGg83bssI0iRBj4O2ZkD6xVmG5YvhdQ=s800-c-k-c0x00ffffff-no-rj'),
    ('nct-dream-q47002841','NCT DREAM','NCT DREAM','2016','UCXURHJRGr4-EB3l87kcbElw','https://www.youtube.com/@nctdream','https://yt3.ggpht.com/zueBt4nWmanBgh4z4W1-S5wbiOIESaXVad_TKTbeHlx97T8fKcbjyX-0iwGaPvZ8BQA1Esyybw=s800-c-k-c0x00ffffff-no-rj'),
    ('nct-wish','NCT WISH','NCT WISH','2024','UCiZqWVAeChfqlom5ZPR3ZJA','https://www.youtube.com/@nctwish','https://yt3.ggpht.com/6XWFHNHfwSFaQWSSYSBqlGnG7bgaKRs-zNGyolItmY_d5uymakA7vDOUKLXYn-aKZdNfwJ6AZoI=s800-c-k-c0x00ffffff-no-rj'),
    ('tws-q124091148','TWS','투어스','2024','UC8C6QOPDVYwmuaSBZksefdg','https://www.youtube.com/@tws_pledis','https://yt3.ggpht.com/oLineVsrAbYEfl8hC4sPloPhni_9Bza78KCAvLsU5lx7jZDW6g1qog4JogzwAnhYRh2rn0t79w=s800-c-k-c0x00ffffff-no-rj'),
    ('illit-q122179261','ILLIT','아일릿','2024','UCEpFoWeCMCo5z3EvWaz6hQQ','https://www.youtube.com/@illit_official','https://yt3.ggpht.com/omgJ9l8hONzRjRJAApTi_6GG-Ok-uV8Qy3g1QIeDKFTlQQ2GjmNowhBpb3MVOYQBukSXy2vCHg=s800-c-k-c0x00ffffff-no-rj'),
    ('kiss-of-life','KISS OF LIFE','키스오브라이프','2023','UCvEEeBssb4XxIfWWIB8IjMw','https://www.youtube.com/@kissoflife_official','https://yt3.ggpht.com/rg6RrMXNkHmx5jY9GAzFkbnH5ue6iDuQLLBxracOstHuiIVEQv5fHVqcXeLM46KQz8WTQBBI8dA=s800-c-k-c0x00ffffff-no-rj'),
    ('stayc-q101541493','STAYC','스테이씨','2020','UCod5V2dpnpJLklGvVOv5FcQ','https://www.youtube.com/@stayc','https://yt3.ggpht.com/vKgYTLMSvA3y1J6bM5-b2VVT9CW6djwVWlZf0e_CGkoeeoJBgPROgCbbNRoCn7bEkPe3taID=s800-c-k-c0x00ffffff-no-rj'),
    ('treasure-q61057550','TREASURE','트레저','2020','UCx9hXYOCvUYwrprEqe4ZQHA','https://www.youtube.com/@treasure','https://yt3.ggpht.com/aUvewrJGTcI4ANkUkWnnwkDr0esbtIrWntgvCb1GWGnRAEKHePNCirzbC2YdoIdKSA0_c63XBQ=s800-c-k-c0x00ffffff-no-rj'),
    ('the-boyz','THE BOYZ','더보이즈','2017','UCO6E0ddL7e1iC_2DC7Po42w','https://www.youtube.com/@officialtheboyz','https://yt3.ggpht.com/q1UxFGIaqpnot2qPXTuJy-WETLv5kT_YFh87IJwi2QIY3KK3o0m-fdJNQtFEtNLNGOROss8UpQ=s800-c-k-c0x00ffffff-no-rj'),
    ('monsta-x-q19855151','MONSTA X','몬스타엑스','2015','UCZvCP6sWj75MwpUP4LVtpNw','https://www.youtube.com/@monstax','https://yt3.ggpht.com/YSAPQp2T7D06Pacn43JA-oZflyNHeuhfUWj2eogKAUwX0wBffUWOsIfC_SgsfNL-P5nP6-apsw=s800-c-k-c0x00ffffff-no-rj'),
    ('shinee-q269836','SHINee','샤이니','2008','UCyPwRgc3gQGqhk6RoGS50Ug','https://www.youtube.com/@shinee','https://yt3.ggpht.com/LBPuKoT9cqeGHOtQDFRWv-WBjhEUcTQScbBAtYck5an9cXzMS2BzRtzRa2-68eZquMI9y9e1QA=s800-c-k-c0x00ffffff-no-rj'),
    ('girls-generation','Girls'' Generation','소녀시대','2007','UCPENYtHg4Xhmm6oX8zaQA7Q','https://www.youtube.com/@girlsgeneration','https://yt3.ggpht.com/IIcbRMbr0HCry1r0pYpVFuW-afpdtv7Jssy2FdoqxDekD8C0Rm8A96SizT03cTRz_3-aXnOAbQ=s800-c-k-c0x00ffffff-no-rj'),
    ('mamamoo-q17278068','MAMAMOO','마마무','2014','UCuhAUMLzJxlP1W7mEk0_6lA','https://www.youtube.com/@mamamoo_official','https://yt3.ggpht.com/V0y6r38_i7SmDNtJRg_HTwIRl6xKVAWcO-YLEDrmdyVSYa0XaYvRrJQt0SJjJYHuRda8_fGYPt0=s800-c-k-c0x00ffffff-no-rj'),
    ('day6-q20898046','DAY6','데이식스','2015','UCp-pqXsizklX3ZHvLxXyhxw','https://www.youtube.com/@day6official','https://yt3.ggpht.com/9l6IIG6X_DWsz0hP482yQZHHeY8UfqYN80c6YTPPNfRf2iYRbusbqUx9ynHzDBbeizr3cyVlL9k=s800-c-k-c0x00ffffff-no-rj'),
    ('qwer','QWER','QWER','2023','UCgD0APk2x9uBlLM0UsmhQjw','https://www.youtube.com/@qwer_band_official','https://yt3.ggpht.com/5qcpNKuhVhrCu-h7axL8l_MUtiTI686T68KfNBmTeKByEDFY6wtRBCBkkT9hlWYVc-SjrKf4m70=s800-c-k-c0x00ffffff-no-rj'),
    ('hearts2hearts-q131746784','Hearts2Hearts','하츠투하츠','2025','UC7Q3HUnJA3nvjZR2JeMn2Cw','https://www.youtube.com/@hearts2hearts.official','https://yt3.ggpht.com/x3ZcA_BPmZ52K1rO0SSP1phM_4KAf1ZYsK_YMwifpl8ihif_MZ4-ylTQBdRW1TJdtHOBcpAdsw=s800-c-k-c0x00ffffff-no-rj'),
    ('kiiikiii-q132526762','KiiiKiii','키키','2025','UCaHwGJXFb28TekZMf7iFg5Q','https://www.youtube.com/@kiiikiii_starship','https://yt3.ggpht.com/FiX2XOR3oZDKJFJREEWlK30eZMTGLmRH8J-9XiqGIbDMo8OGviVlczUhr1EiIjdSRyVhr_1L_6c=s800-c-k-c0x00ffffff-no-rj'),
    ('allday-project','ALLDAY PROJECT','올데이 프로젝트','2025','UCKOY4n0sv1pAPs5E4LxtSXQ','https://www.youtube.com/@allday_project','https://yt3.ggpht.com/KlKnNaef1rJVk4GVe1wlz6ISIEvDn0iuJcsfX8IJ7KcCOLqEPiXQy9RDUgikzWPgYdwisInuxw=s800-c-k-c0x00ffffff-no-rj')
)
insert into public.artists(
  slug,name,name_ko,image_url,description,role_description,debut_text,active,
  review_pending,profile_image_source_provider,profile_image_source_url,
  profile_image_source_collected_at,youtube_channel_id
)
select slug,name,name_ko,thumbnail_url,
       name_ko || '는 대한민국에서 활동하는 K-POP 아티스트입니다.',
       'K-POP 아티스트',debut_text,false,true,'YouTube Data API',channel_url,now(),channel_id
from official_artist
on conflict (slug) do update
set image_url=excluded.image_url,
    review_pending=case when public.artists.active then false else true end,
    profile_image_source_provider=excluded.profile_image_source_provider,
    profile_image_source_url=excluded.profile_image_source_url,
    profile_image_source_collected_at=excluded.profile_image_source_collected_at,
    youtube_channel_id=excluded.youtube_channel_id,
    updated_at=now();

do $$
declare matched integer;
begin
  select count(*) into matched
  from public.artists
  where youtube_channel_id in (
      'UCritGVo7pLJLUS8wEu32vow','UCdVD0MsYecQaIE5Ru-pOIQQ','UChhKBlh_wvspTh5n4mL0b5g',
      'UCXURHJRGr4-EB3l87kcbElw','UCiZqWVAeChfqlom5ZPR3ZJA','UC8C6QOPDVYwmuaSBZksefdg',
      'UCEpFoWeCMCo5z3EvWaz6hQQ','UCvEEeBssb4XxIfWWIB8IjMw','UCod5V2dpnpJLklGvVOv5FcQ',
      'UCx9hXYOCvUYwrprEqe4ZQHA','UCO6E0ddL7e1iC_2DC7Po42w','UCZvCP6sWj75MwpUP4LVtpNw',
      'UCyPwRgc3gQGqhk6RoGS50Ug','UCPENYtHg4Xhmm6oX8zaQA7Q','UCuhAUMLzJxlP1W7mEk0_6lA',
      'UCp-pqXsizklX3ZHvLxXyhxw','UCgD0APk2x9uBlLM0UsmhQjw','UC7Q3HUnJA3nvjZR2JeMn2Cw',
      'UCaHwGJXFb28TekZMf7iFg5Q','UCKOY4n0sv1pAPs5E4LxtSXQ'
    );
  if matched <> 20 then
    raise exception 'Expected 20 staged artists with verified YouTube profiles, found %', matched;
  end if;
end $$;
