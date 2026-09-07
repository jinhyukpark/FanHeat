alter table public.artists
  add column if not exists profile_image_fallback_url text,
  add column if not exists profile_image_source_provider text,
  add column if not exists profile_image_source_url text,
  add column if not exists profile_image_source_collected_at timestamptz,
  add column if not exists youtube_channel_id text;

comment on column public.artists.profile_image_fallback_url is 'Previous verified artist image used when a remote official channel thumbnail is unavailable.';
comment on column public.artists.profile_image_source_provider is 'Provider that supplied the current profile image.';
comment on column public.artists.profile_image_source_url is 'Official source page for the current profile image.';
comment on column public.artists.profile_image_source_collected_at is 'Time the remote profile image metadata was verified.';
comment on column public.artists.youtube_channel_id is 'Verified official YouTube channel ID.';

with official_channel(slug, channel_id, channel_url, thumbnail_url) as (
  values
    ('kwon-eun-bi-q56505060', 'UConJnFkj7YTb8FaysHfGpPw', 'https://www.youtube.com/@kwoneunbi_official', 'https://yt3.ggpht.com/JYX5gGdfmYhCwFjCA_bPQ5NbJ2TpQwkxGZgjUSAmtizl0ehApZYh5Fyuu5anNoxfjsIkt74L=s800-c-k-c0x00ffffff-no-rj'),
    ('bts-q13580495', 'UCLkAepWjdylmXSltofFvsYQ', 'https://www.youtube.com/@bts', 'https://yt3.ggpht.com/NNG93LntJGDpMlGYIhavu2n4gREs7CNbNT8jjG-7dpotBa5uQDHhuOL8e_oU4ihzWhlwdCmsJw0=s800-c-k-c0x00ffffff-no-rj'),
    ('blackpink-q25056945', 'UCOmHUn--16B90oW2L6FRR3A', 'https://www.youtube.com/@blackpink', 'https://yt3.ggpht.com/U3VrCkKjzTpQ3VYv4SCPjNfDHeJV-swGNnhLYhr0nV4lZz_GVUNzK4EB-HFRfKv9S5VNh14uAg=s800-c-k-c0x00ffffff-no-rj'),
    ('twice-q20645861', 'UCzgxx_DM2Dcb9Y1spb9mUJA', 'https://www.youtube.com/@twice', 'https://yt3.ggpht.com/rj-m7CQIV8hIHx_lB8cjs0NxrDFJaUkVwZ5tCnZTNSVEr2IqXGF-2e7nr7og1IGeRXtHikce=s800-c-k-c0x00ffffff-no-rj'),
    ('stray-kids-q46134670', 'UC9rMiEjNaCSsebs31MRDCRA', 'https://www.youtube.com/@straykids', 'https://yt3.ggpht.com/CIofqs6QaCJq7bD8vo_C1__1udt4A7rIpbnOna8v09Q2NPlO5F-rAmAxZKciQRY0w-_40XEA2pA=s800-c-k-c0x00ffffff-no-rj'),
    ('seventeen-q14524548', 'UCfkXDY7vwkcJ8ddFGz8KusA', 'https://www.youtube.com/@pledis17', 'https://yt3.ggpht.com/ZGqaImntHbCllA_dkYLrc5kH8JE1KNSy2bP7vkWsXjFXgNSzsP2it9qHh7oaQLLJL25B48C2TA=s800-c-k-c0x00ffffff-no-rj'),
    ('aespa-q100877982', 'UC9GtSLeksfK4yuJ_g1lgQbg', 'https://www.youtube.com/@aespa', 'https://yt3.ggpht.com/ViYqIYAJTZj5RmgEdO-ob0WUtUW3uMZrLq3J7mHL0EX-VZf5KBJTid75w7Ojq5lbBTq-sHYa-pY=s800-c-k-c0x00ffffff-no-rj'),
    ('ive-q109375061', 'UC-Fnix71vRP64WXeo0ikd0Q', 'https://www.youtube.com/@ivestarship', 'https://yt3.ggpht.com/_CyiM1Ob0gRzu4d3Y4-l1vJTyZSRld8OR7oJ9PmtLNdDMtN0koRRs_asLpIEsSGmKAwEKK_CTqs=s800-c-k-c0x00ffffff-no-rj'),
    ('le-sserafim-q111381707', 'UCs-QBT4qkj_YiQw1ZntDO3g', 'https://www.youtube.com/@lesserafim_official', 'https://yt3.ggpht.com/eLnV_fwQLMbjKZPkA8QzzLusBAHgG3cQ-QmQQ6nMSXYXanHgPL6snGMAvb3pst8QC8mVgiLKsQ=s800-c-k-c0x00ffffff-no-rj'),
    ('newjeans-q113189277', 'UCMki_UkHb4qSc0qyEcOHHJw', 'https://www.youtube.com/@newjeans_official', 'https://yt3.ggpht.com/seIPyT29v_T3KcqQ1aHoAC8qHBVH4Pz4pPa1qpZL623ypce3of75-uA5US-TZyk5WwZLUO0n3A=s800-c-k-c0x00ffffff-no-rj'),
    ('enhypen-q99479445', 'UCArLZtok93cO5R9RI4_Y5Jw', 'https://www.youtube.com/@enhypenofficial', 'https://yt3.ggpht.com/DZ3yFL6peM3ASY-9ndbMPaiwac3-VrCDLxhO3WigI60mCahs0GQZuv0SFIbH1TmrPUWrlwEV=s800-c-k-c0x00ffffff-no-rj'),
    ('tomorrow-x-together-q60550265', 'UCtiObj3CsEAdNU6ZPWDsddQ', 'https://www.youtube.com/@txt_bighit', 'https://yt3.ggpht.com/BduyBJNA9Id8u23W2MEMyNiH7uDzwL0p5A4XqMcOuggTML_xHSzvj_Oq8SWSW9lJabdqzwWIpg=s800-c-k-c0x00ffffff-no-rj'),
    ('ateez-q59793088', 'UC2e4Ukj5Pfr7cb3KpJAFBdQ', 'https://www.youtube.com/@ateezofficial', 'https://yt3.ggpht.com/M_RKZsb4YRL8uunqGIlLOT3Qd9nLMbdcdBrOyH3fOi3yLxh0YBH4pTxfydlUv2KktrcKVujzH9o=s800-c-k-c0x00ffffff-no-rj'),
    ('exo-q494717', 'UCzCedBCSSltI1TFd3bKyN6g', 'https://www.youtube.com/@weareoneexo', 'https://yt3.ggpht.com/ujB2n35HjiBrD1UHWY6aLdZJ4-g01agipoXe2NFQaAbuEhnIPnJHbrfi9ScdgawZWSuKZkPGhg=s800-c-k-c0x00ffffff-no-rj'),
    ('red-velvet-q17466114', 'UCk9GmdlDTBfgGRb7vXeRMoQ', 'https://www.youtube.com/@redvelvet', 'https://yt3.ggpht.com/tlpg9ruan35dhpWmHD_ZmEBt-fcTnF32GHIt7Yml_pW8kpRQInrbNL9oalMHpeD7QRq2xzQY8Dg=s800-c-k-c0x00ffffff-no-rj'),
    ('itzy-q60732823', 'UCDhM2k2Cua-JdobAh5moMFg', 'https://www.youtube.com/@itzy', 'https://yt3.ggpht.com/7mseSxNNVqaEHWf8X8IiJwJFHyA8PGXpFriAAtZNcuq6PrW7Kx2JDDRViKaODn7uekjwAs02MQ=s800-c-k-c0x00ffffff-no-rj'),
    ('nmixx-q109307762', 'UCnUAyD4t2LkvW68YrDh7fDg', 'https://www.youtube.com/@nmixxofficial', 'https://yt3.ggpht.com/67GqZ7FPYeBoHqvJhrvm3L0nmAe4hwM7lh_9O0JHKoBGe_bo6mPR9mUnXZ5gWDini2t7ss-v=s800-c-k-c0x00ffffff-no-rj'),
    ('babymonster-q115967938', 'UCqwUnggBBct-AY2lAdI88jQ', 'https://www.youtube.com/@babymonster', 'https://yt3.ggpht.com/guzIoEyd9IyKWaD7Jfnlp1rD7k9SiEOV7go0ItyJ3O9V-j8ez6Jvs4Yj3LfrCu3Z7rFcdIqYLTI=s800-c-k-c0x00ffffff-no-rj'),
    ('zerobaseone-q117808633', 'UCSAp0Yl9S0Zq5uDqE6im_XQ', 'https://www.youtube.com/@zb1_official', 'https://yt3.ggpht.com/Hg4ZbB2y-VfSy7dijJm5_FZYogifOd7Yc1sBXPz3jjaBznUEgsPXSrULf-WVmzjiCOLOa7o_gg=s800-c-k-c0x00ffffff-no-rj'),
    ('nct-127-q55624444', 'UCk2E0dbAyEJWnrN2bbQOcbg', 'https://www.youtube.com/@nct127', 'https://yt3.ggpht.com/l9D9SH_XlAECnTVZsvo0jM2o9GKmqjOVXQAWy-Xgy2EK8WLPVSODVP3I-bowl0ys1biuTXcfmg=s800-c-k-c0x00ffffff-no-rj')
)
update public.artists artist
set profile_image_fallback_url = coalesce(nullif(artist.profile_image_fallback_url, ''), nullif(artist.image_url, '')),
    image_url = official_channel.thumbnail_url,
    profile_image_source_provider = 'YouTube Data API',
    profile_image_source_url = official_channel.channel_url,
    profile_image_source_collected_at = now(),
    youtube_channel_id = official_channel.channel_id,
    updated_at = now()
from official_channel
where artist.slug = official_channel.slug;

do $$
declare
  synced_count integer;
begin
  select count(*) into synced_count
  from public.artists
  where active = true
    and profile_image_source_provider = 'YouTube Data API'
    and youtube_channel_id is not null
    and image_url like 'https://yt3.ggpht.com/%';

  if synced_count <> 20 then
    raise exception 'Expected 20 verified YouTube profile images, found %', synced_count;
  end if;
end
$$;
