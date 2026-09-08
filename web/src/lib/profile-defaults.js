const SYSTEM_ASSET_BASE = 'https://yuiemljibxeoifupvluc.supabase.co/storage/v1/object/public/fanheat-assets/3207765e-4d0a-4c9c-b620-46a805ca0ee7/system/'

export const PROFILE_DISPLAY_DEFAULTS = Object.freeze({
  avatar_url: `${SYSTEM_ASSET_BASE}mypage.jpg`,
  cover_url: '/images/auth-concert.jpg',
  profile_headline: '',
  bio: '',
  facebook_url: '',
  x_url: '',
  instagram_url: '',
  tiktok_url: '',
  youtube_url: '',
  favorite_track_id: null,
})

const textOrDefault = (value, fallback = '') => typeof value === 'string' && value.trim() ? value.trim() : fallback

const LEGACY_PROFILE_HEADLINE = '좋아하는 음악과 아티스트의 순간을 모아 팬들과 함께 나누고 있습니다.'
const LEGACY_PROFILE_BIO = '음악과 무대를 사랑하는 FAN HEAT 사용자입니다. 새로운 앨범과 공연 소식을 발견하고, 좋아하는 아티스트에 대한 이야기를 팬들과 함께 나눕니다.'
const LEGACY_PROFILE_COVER = `${SYSTEM_ASSET_BASE}mypage_bg.jpg`
const legacySocialUrls = new Set(['https://www.facebook.com/', 'https://x.com/', 'https://www.instagram.com/'])
const isLegacyCover = value => {
  const url = textOrDefault(value)
  return url === 'mypage_bg.jpg' || url === '/images/mypage_bg.jpg' || url === LEGACY_PROFILE_COVER
}

export const withProfileDisplayDefaults = (profile = {}) => {
  const storedHeadline = textOrDefault(profile.profile_headline)
  const headline = storedHeadline.startsWith(LEGACY_PROFILE_HEADLINE) ? '' : storedHeadline
  const bio = textOrDefault(profile.bio) === LEGACY_PROFILE_BIO ? '' : textOrDefault(profile.bio)
  const coverUrls = (profile.cover_urls || []).filter(url => url && !isLegacyCover(url))
  const coverUrl = isLegacyCover(profile.cover_url) ? '' : textOrDefault(profile.cover_url)
  const socialUrl = value => legacySocialUrls.has(textOrDefault(value)) ? '' : textOrDefault(value)
  return {
    ...PROFILE_DISPLAY_DEFAULTS,
    ...profile,
    _profile_headline_is_set: Boolean(headline),
    _bio_is_set: Boolean(bio),
    _cover_is_set: Boolean(coverUrl || coverUrls.length),
    avatar_url: textOrDefault(profile.avatar_url, PROFILE_DISPLAY_DEFAULTS.avatar_url),
    cover_url: textOrDefault(coverUrl, PROFILE_DISPLAY_DEFAULTS.cover_url),
    cover_urls: coverUrls,
    profile_headline: headline,
    bio,
    facebook_url: socialUrl(profile.facebook_url),
    x_url: socialUrl(profile.x_url),
    instagram_url: socialUrl(profile.instagram_url),
    tiktok_url: textOrDefault(profile.tiktok_url),
    youtube_url: textOrDefault(profile.youtube_url),
    favorite_track_id: profile.favorite_track_id ?? PROFILE_DISPLAY_DEFAULTS.favorite_track_id,
  }
}
