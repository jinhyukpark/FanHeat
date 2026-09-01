const SYSTEM_ASSET_BASE = 'https://yuiemljibxeoifupvluc.supabase.co/storage/v1/object/public/fanheat-assets/3207765e-4d0a-4c9c-b620-46a805ca0ee7/system/'

export const PROFILE_DISPLAY_DEFAULTS = Object.freeze({
  avatar_url: `${SYSTEM_ASSET_BASE}mypage.jpg`,
  cover_url: `${SYSTEM_ASSET_BASE}mypage_bg.jpg`,
  profile_headline: '좋아하는 음악과 아티스트의 순간을 모아 팬들과 함께 나누고 있습니다.',
  bio: '음악과 무대를 사랑하는 FAN HEAT 사용자입니다. 새로운 앨범과 공연 소식을 발견하고, 좋아하는 아티스트에 대한 이야기를 팬들과 함께 나눕니다.',
  facebook_url: 'https://www.facebook.com/',
  x_url: 'https://x.com/',
  instagram_url: 'https://www.instagram.com/',
  tiktok_url: '',
  youtube_url: '',
  favorite_track_id: null,
})

const textOrDefault = (value, fallback = '') => typeof value === 'string' && value.trim() ? value.trim() : fallback

export const withProfileDisplayDefaults = (profile = {}) => ({
  ...PROFILE_DISPLAY_DEFAULTS,
  ...profile,
  avatar_url: textOrDefault(profile.avatar_url, PROFILE_DISPLAY_DEFAULTS.avatar_url),
  cover_url: textOrDefault(profile.cover_url, PROFILE_DISPLAY_DEFAULTS.cover_url),
  profile_headline: textOrDefault(profile.profile_headline, PROFILE_DISPLAY_DEFAULTS.profile_headline),
  bio: textOrDefault(profile.bio, PROFILE_DISPLAY_DEFAULTS.bio),
  facebook_url: textOrDefault(profile.facebook_url, PROFILE_DISPLAY_DEFAULTS.facebook_url),
  x_url: textOrDefault(profile.x_url, PROFILE_DISPLAY_DEFAULTS.x_url),
  instagram_url: textOrDefault(profile.instagram_url, PROFILE_DISPLAY_DEFAULTS.instagram_url),
  tiktok_url: textOrDefault(profile.tiktok_url),
  youtube_url: textOrDefault(profile.youtube_url),
  favorite_track_id: profile.favorite_track_id ?? PROFILE_DISPLAY_DEFAULTS.favorite_track_id,
})
