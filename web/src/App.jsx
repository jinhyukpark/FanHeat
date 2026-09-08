import ArtistCorrectionDialog from './ArtistCorrectionDialog'
import { useEffect, useMemo, useRef, useState } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import { createPortal } from 'react-dom'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import Youtube from '@tiptap/extension-youtube'
import DOMPurify from 'dompurify'
import { supabase } from './lib/supabase'
import { loadPublicProfileFriends } from './lib/api'
import { addComment, cancelFriendRequest, castDailyArtistVote, deleteComment, deleteProfileGalleryImage, loadArtistEngagement, loadBestFriends, loadCommentReactions, loadComments, loadDailyArtistVotes, loadFanStats, loadFriendshipStatus, loadHomeData, loadMessageBlocks, loadMessageContacts, loadPostBookmark, loadPostVote, loadPrivateMessages, loadProfileCustomization, loadProfileGallery, loadUnreadMessageCount, loadUserBookmarks, loadUserComments, markPrivateMessageRead, publishPost, recordArtistClick, recordPostView, saveProfileCustomization, sendFriendRequest, sendPrivateMessage, setArtistFanRegistration, setArtistFollowing, setCommentReaction, setMessageBlock, setPostBookmark, setPostVote, submitFanPhotos, updateComment, updatePost, uploadProfileGalleryImages } from './lib/api'
import { calculateFanLevel, calculateFanRank } from './lib/fan-stats'
import { MAX_FEATURED_MEDIA_COUNT } from './lib/post-limits'
import { PROFILE_DISPLAY_DEFAULTS, withProfileDisplayDefaults } from './lib/profile-defaults'
import { I18nProvider, useI18n } from './i18n'
import AdminApp from './AdminApp'
import LegalPage from './LegalPage'
import CopyrightReportDialog from './CopyrightReportDialog'
import './hero-carousel.css'
import './list-number.css'
import './star-page.css'
import './my-page.css'

const A = 'https://yuiemljibxeoifupvluc.supabase.co/storage/v1/object/public/fanheat-assets/3207765e-4d0a-4c9c-b620-46a805ca0ee7/system/'
// 사용자 음악 재생은 서비스 방향이 확정될 때까지 임시 비활성화합니다.
// 추후 재개할 때 이 값만 true로 변경하면 보관된 재생 UI와 로직이 다시 노출됩니다.
const USER_MUSIC_PLAYBACK_ENABLED = false
// 글쓰기 음원 첨부 UI는 서비스 방향 확정 전까지 숨긴다. 다시 제공할 때 true로 변경한다.
const POST_MUSIC_ATTACHMENT_ENABLED = false
const assetSrc = value => {
  const source = String(value || '').trim()
  if (!source) return ''
  return /^https?:\/\//.test(source) || source.startsWith('/') ? source : `${A}${source}`
}

function useSwipeCarousel({ length, index, onChange, threshold = 32 }) {
  const gesture = useRef(null)
  const [dragOffset, setDragOffset] = useState(0)
  const [dragging, setDragging] = useState(false)
  const reset = event => {
    const active = gesture.current
    if (active && event?.currentTarget?.hasPointerCapture?.(active.pointerId)) event.currentTarget.releasePointerCapture(active.pointerId)
    gesture.current = null
    setDragOffset(0)
    setDragging(false)
  }
  const bind = {
    onPointerDown: event => {
      if (length < 2 || (event.pointerType === 'mouse' && event.button !== 0) || event.target.closest('button,a,input')) return
      gesture.current = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, axis: null }
      setDragging(true)
      event.currentTarget.setPointerCapture?.(event.pointerId)
    },
    onPointerMove: event => {
      const active = gesture.current
      if (!active || active.pointerId !== event.pointerId) return
      const distanceX = event.clientX - active.startX
      const distanceY = event.clientY - active.startY
      if (!active.axis && Math.max(Math.abs(distanceX), Math.abs(distanceY)) >= 6) active.axis = Math.abs(distanceX) > Math.abs(distanceY) ? 'x' : 'y'
      if (active.axis !== 'x') return
      event.preventDefault()
      setDragOffset(Math.max(-96, Math.min(96, distanceX)))
    },
    onPointerUp: event => {
      const active = gesture.current
      if (!active || active.pointerId !== event.pointerId) return
      const distanceX = event.clientX - active.startX
      if (active.axis === 'x' && Math.abs(distanceX) >= threshold) onChange((index + (distanceX < 0 ? 1 : -1) + length) % length, distanceX < 0 ? 'next' : 'prev')
      reset(event)
    },
    onPointerCancel: reset,
  }
  return { bind, dragOffset, dragging }
}

const youtubeVideoId = value => {
  if (!value) return ''
  try {
    const url = new URL(value)
    const host = url.hostname.replace(/^www\./, '')
    const pathParts = url.pathname.split('/').filter(Boolean)
    if (host !== 'youtu.be' && !['youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtube-nocookie.com'].includes(host)) return ''
    const id = host === 'youtu.be'
      ? pathParts[0]
      : url.searchParams.get('v') || (['embed', 'shorts', 'live'].includes(pathParts[0]) ? pathParts[1] : '')
    return /^[A-Za-z0-9_-]{6,15}$/.test(id || '') ? id : ''
  } catch { return '' }
}
const youtubeEmbedUrl = value => {
  const id = youtubeVideoId(value)
  return id ? `https://www.youtube-nocookie.com/embed/${id}` : ''
}
const youtubeThumbnailUrl = (value, quality = 'hqdefault') => {
  const id = youtubeVideoId(value)
  return id ? `https://i.ytimg.com/vi/${id}/${quality}.jpg` : ''
}
const safeExternalUrl = value => {
  try {
    const url = new URL(value || '')
    return ['http:', 'https:'].includes(url.protocol) ? url.href : ''
  } catch { return '' }
}
const safeRichHtml = value => {
  const sanitized = DOMPurify.sanitize(value || '', {
    ADD_TAGS: ['iframe'],
    ADD_ATTR: ['allow', 'allowfullscreen', 'frameborder', 'data-youtube-video', 'referrerpolicy', 'sandbox'],
    FORBID_ATTR: ['srcdoc'],
  })
  if (typeof document === 'undefined') return sanitized
  const template = document.createElement('template')
  template.innerHTML = sanitized
  template.content.querySelectorAll('iframe').forEach(frame => {
    const embedUrl = youtubeEmbedUrl(frame.getAttribute('src'))
    if (!embedUrl) {
      frame.remove()
      return
    }
    frame.setAttribute('src', embedUrl)
    frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-presentation allow-popups')
    frame.setAttribute('referrerpolicy', 'strict-origin-when-cross-origin')
  })
  template.content.querySelectorAll('a').forEach(link => {
    const href = safeExternalUrl(link.getAttribute('href'))
    if (!href) {
      link.removeAttribute('href')
      return
    }
    link.setAttribute('href', href)
    link.setAttribute('rel', 'noopener noreferrer')
  })
  return template.innerHTML
}
const richHtmlWithImageCredits = (value, imageSources = []) => {
  const sanitized = safeRichHtml(value)
  if (typeof document === 'undefined' || !imageSources.length) return sanitized
  const template = document.createElement('template')
  template.innerHTML = sanitized
  const sourcesByImage = new Map(imageSources
    .filter(source => source?.image_url)
    .map(source => [source.image_url, source]))
  template.content.querySelectorAll('img[src]').forEach((image, index) => {
    const source = sourcesByImage.get(image.getAttribute('src')) || imageSources[index]
    const sourceUrl = safeExternalUrl(source?.source_url || source?.url)
    const sourceLabel = String(source?.source_label || source?.label || '').trim()
    if (!sourceUrl && !sourceLabel) return
    const credit = document.createElement('span')
    credit.className = 'inline-image-source-credit'
    const prefix = document.createElement('span')
    prefix.textContent = '이미지 출처'
    credit.append(prefix)
    const label = attributionLabel(sourceLabel, sourceUrl, '원본 이미지')
    if (sourceUrl) {
      const link = document.createElement('a')
      link.href = sourceUrl
      link.target = '_blank'
      link.rel = 'noopener noreferrer'
      link.textContent = `${label} ↗`
      credit.append(link)
    } else {
      const text = document.createElement('strong')
      text.textContent = label
      credit.append(text)
    }
    image.insertAdjacentElement('afterend', credit)
  })
  return template.innerHTML
}
const highResolutionFallbacks = ['rescene-jacket.jpeg', 'ive-jacket.jpeg', 'bingle_bangle.jpg', 'mypage.jpg', 'rescene-bg.jpeg', 'ive-bg.jpeg', 'post2.jpg', 'mypage_bg.jpg']
const starCopy = {
  '아이유': { realName: '아이유 (이지은)', role: '싱어송라이터 · 배우', debut: '2008년 9월 18일', agency: 'EDAM 엔터테인먼트', fandom: 'UAENA', bio: ['아이유는 섬세한 감성과 폭넓은 음악적 스펙트럼으로 사랑받는 대한민국의 싱어송라이터이자 배우입니다. 직접 작사와 작곡에 참여하며 세대와 장르를 아우르는 독자적인 음악 세계를 만들어 왔습니다.', '음악 활동과 연기 활동을 함께 이어가며 무대, 드라마, 영화 등 다양한 영역에서 자신만의 이야기를 전하고 있습니다. 팬들과 꾸준히 소통하고 공연을 통해 완성도 높은 라이브 무대를 선보입니다.'] },
  '워너원': { realName: '워너원 (Wanna One)', role: '보이 그룹', debut: '2017년 8월 7일', agency: 'Swing 엔터테인먼트', fandom: 'WANNABLE' },
  '빅뱅': { realName: 'BIGBANG', role: '보이 그룹', debut: '2006년 8월 19일', agency: 'YG 엔터테인먼트', fandom: 'V.I.P' },
  '씨스타': { realName: 'SISTAR', role: '걸 그룹', debut: '2010년 6월 3일', agency: 'Starship 엔터테인먼트', fandom: 'STAR1', heroImage: 'hires/sistar-hero.jpg', imageCredit: 'mduangdara · CC BY-SA 2.0', imageCreditUrl: 'https://commons.wikimedia.org/wiki/File:KCON_2015_Sistar.jpg' },
  '트와이스': { realName: 'TWICE', role: '걸 그룹', debut: '2015년 10월 20일', agency: 'JYP 엔터테인먼트', fandom: 'ONCE' },
  '레드벨벳': { realName: 'Red Velvet', role: '걸 그룹', debut: '2014년 8월 1일', agency: 'SM 엔터테인먼트', fandom: 'ReVeluv' },
  '엑소': { realName: 'EXO', role: '보이 그룹', debut: '2012년 4월 8일', agency: 'SM 엔터테인먼트', fandom: 'EXO-L' },
  '블랙핑크': { realName: 'BLACKPINK', role: '걸 그룹', debut: '2016년 8월 8일', agency: 'YG 엔터테인먼트', fandom: 'BLINK' },
}

const starGalleryFallbacks = {
  '아이유': ['award2.jpg', 'post_list4.jpg', 'music2.jpg'],
  '워너원': ['award1.jpg', 'chart12.jpg', 'music8.jpg'],
  '빅뱅': ['award3.jpg', 'chart3.jpg', 'music7.jpg'],
  '씨스타': ['hires/sistar-hero.jpg', 'award4.jpg', 'post_list3.jpg'],
  '트와이스': ['award1.jpg', 'post_list2.jpg', 'chart3.jpg'],
  '레드벨벳': ['award2.jpg', 'post_list3.jpg', 'chart6.jpg'],
  '엑소': ['award3.jpg', 'chart10.jpg', 'music8.jpg'],
  '블랙핑크': ['award4.jpg', 'chart8.jpg', 'post_list5.jpg'],
}

const artistTopTracks = {
  '아이유': ['좋은 날', '밤편지', '팔레트', 'Blueming', 'Love wins all'],
  '워너원': ['에너제틱', 'Beautiful', '봄바람', 'BOOMERANG', '켜줘'],
  '빅뱅': ['거짓말', '하루하루', 'FANTASTIC BABY', '뱅뱅뱅', '봄여름가을겨울'],
  '씨스타': ['Touch My Body', 'SHAKE IT', 'Loving U', '나 혼자', 'I Swear'],
  '트와이스': ['CHEER UP', 'TT', 'What is Love?', 'FANCY', 'Feel Special'],
  '레드벨벳': ['빨간 맛', 'Psycho', 'Bad Boy', 'Feel My Rhythm', 'Queendom'],
  '엑소': ['으르렁', 'CALL ME BABY', 'Love Shot', 'Tempo', '첫 눈'],
  '블랙핑크': ['DDU-DU DDU-DU', 'Kill This Love', 'How You Like That', 'Pink Venom', 'Shut Down'],
  '샤운': ['Way Back Home', 'Bad Habits', '36.5', 'Dream', 'Terminal'],
  '순': ['Way Back Home', 'Bad Habits', '36.5', 'Dream', 'Terminal'],
  'SHAUN': ['Way Back Home', 'Bad Habits', '36.5', 'Dream', 'Terminal'],
  '마마무': ['HIP', '별이 빛나는 밤', '넌 is 뭔들', 'Décalcomanie', '딩가딩가'],
  '에이핑크': ['NoNoNo', 'Mr. Chu', 'LUV', '덤더럼', 'Dilemma'],
  '청하': ['Roller Coaster', '벌써 12시', 'Snapping', 'Gotta Go', 'Sparkling'],
}

const catalogTopTracks = (artist, fallbackName) => {
  const albums = [...(artist?.artist_albums || [])]
    .filter(album => album?.active !== false)
    .sort((a, b) => Number(a.display_order || 0) - Number(b.display_order || 0) || String(b.release_date || '').localeCompare(String(a.release_date || '')))
  const candidates = [
    ...albums.map(album => album.lead_track),
    ...albums.flatMap(album => [...(album.artist_album_tracks || [])]
      .filter(track => track?.active !== false)
      .sort((a, b) => Number(a.display_order || a.track_number || 0) - Number(b.display_order || b.track_number || 0))
      .map(track => track.title)),
    ...(artistTopTracks[fallbackName] || artistTopTracks[artist?.name] || []),
  ]
  const seen = new Set()
  return candidates.map(value => String(value || '').trim()).filter(value => {
    const key = value.toLocaleLowerCase()
    if (!value || seen.has(key)) return false
    seen.add(key)
    return true
  }).slice(0, 5)
}

const isApprovedArtistGalleryItem = item => item?.active === true && item?.review_status === 'approved'

const makeStarProfile = ([name, score, image, data]) => {
  const galleryItems = [...(data?.artist_gallery_items || [])].filter(isApprovedArtistGalleryItem).sort((a, b) => Number(a.display_order || 0) - Number(b.display_order || 0))
  const gallery = galleryItems.map(item => item.image_url).filter(Boolean)
  const displayImage = data?.hero_image_url || image
  const displayCredit = galleryItems.find(item => item.image_url === displayImage || item.original_image_url === displayImage)
  const profileImages = [...(data?.artist_profile_images || [])].sort((a, b) => Number(a.display_order || 0) - Number(b.display_order || 0)).map(item => item.image_url).filter(Boolean)
  return {
    id: data?.id || name,
    name,
    image,
    profileImages: profileImages.length ? profileImages : [image].filter(Boolean),
    realName: data?.real_name || name,
    role: data?.role_description || '정보 미등록',
    debut: data?.debut_text || '정보 미등록',
    agency: data?.agency || '정보 미등록',
    fandom: data?.fandom_name || '정보 미등록',
    heroImage: displayImage,
    imageCredit: displayCredit?.attribution_text || '',
    imageCreditUrl: displayCredit?.source_page_url || '',
    description: data?.description || '',
    gallery,
    galleryItems,
    albums: [...(data?.artist_albums || [])].sort((a, b) => Number(a.display_order || 0) - Number(b.display_order || 0)),
    fans: dedupeArtistFans(data?.artist_fans || []),
    history: Array.isArray(data?.history_items) ? data.history_items : [],
    awards: Array.isArray(data?.award_items) ? data.award_items : [],
    followers: Number(data?.follower_count || 0) || Number(String(score).replace(/,/g, '')) || 0,
    visitorToday: Number(data?.visitor_today || 0),
    visitorTotal: Number(data?.visitor_total || 0),
    facebookUrl: data?.facebook_url || '',
    xUrl: data?.x_url || '',
    instagramUrl: data?.instagram_url || '',
    bio: data?.bio_paragraphs?.length ? data.bio_paragraphs : (data?.description ? [data.description] : []),
  }
}

const dedupeArtistFans = fans => {
  const unique = []
  const profileIds = new Set()
  const handles = new Set()
  ;[...fans]
    .sort((a, b) => Number(Boolean(b.profile_id)) - Number(Boolean(a.profile_id)) || Number(a.display_order || 0) - Number(b.display_order || 0))
    .forEach(fan => {
      const profileId = fan?.profile_id || ''
      const handle = String(fan?.handle || '').trim().toLowerCase()
      if (profileId ? profileIds.has(profileId) : (handle && handles.has(handle))) return
      if (profileId) profileIds.add(profileId)
      if (handle) handles.add(handle)
      unique.push(fan)
    })
  return unique.sort((a, b) => Number(a.display_order || 0) - Number(b.display_order || 0))
}

const keywordStopWords = new Set(['그리고', '그러나', '대한', '관련', '사진', '영상', '오늘', '이번', '공개', '최신', '소식', '포스트', '팬히트', 'fanheat', 'the', 'and', 'with', 'from'])
const trendingPostKeywords = (items = [], limit = 5) => {
  const keywords = new Map()
  const add = (value, weight, index) => {
    const label = String(value || '').replace(/^#+/, '').trim()
    const key = label.toLocaleLowerCase('ko-KR')
    if (label.length < 2 || label.length > 24 || keywordStopWords.has(key) || /^\d+$/.test(label)) return
    const current = keywords.get(key) || { label, score: 0, uses: 0, firstIndex: index }
    current.score += weight
    current.uses += 1
    current.firstIndex = Math.min(current.firstIndex, index)
    keywords.set(key, current)
  }

  items.forEach(([title, , data], index) => {
    const seenTags = new Set()
    const tags = Array.isArray(data?.tags) ? data.tags : String(data?.tags || '').split(',')
    tags.forEach(tag => {
      const normalized = String(tag || '').replace(/^#+/, '').trim().toLocaleLowerCase('ko-KR')
      if (!normalized || seenTags.has(normalized)) return
      seenTags.add(normalized)
      add(tag, 3, index)
    })
    const seenTitleWords = new Set()
    String(title || '').split(/[\s+·|/()[\]{}<>,.!?:;~\-_]+/u).forEach(word => {
      const normalized = word.trim().toLocaleLowerCase('ko-KR')
      if (!normalized || seenTitleWords.has(normalized)) return
      seenTitleWords.add(normalized)
      add(word, 1, index)
    })
  })

  return [...keywords.values()]
    .sort((a, b) => b.score - a.score || b.uses - a.uses || a.firstIndex - b.firstIndex || a.label.localeCompare(b.label, 'ko'))
    .slice(0, Math.max(3, Math.min(5, limit)))
    .map(item => item.label)
}

const serviceNotices = [
  {
    id: 'welcome-2026-08',
    category: '서비스',
    title: 'FAN HEAT에 오신 것을 환영합니다',
    summary: '더 즐겁고 안전하게 FAN HEAT을 이용하는 방법을 안내해 드립니다.',
    publishedAt: '2026. 8. 28.',
    body: ['FAN HEAT은 좋아하는 아티스트와 팬들의 이야기를 함께 나누는 공간입니다.', '서로를 존중하는 표현을 사용해 주세요. 게시글과 댓글, 쪽지에서 불편한 콘텐츠를 발견하면 고객지원으로 알려주시면 빠르게 확인하겠습니다.'],
  },
  {
    id: 'community-update-2026-08',
    category: '업데이트',
    title: '마이페이지와 쪽지 기능이 새로워졌어요',
    summary: '내 활동을 한곳에서 확인하고 팬들과 편하게 쪽지를 주고받을 수 있습니다.',
    publishedAt: '2026. 8. 24.',
    body: ['마이페이지에서 내가 작성한 포스트와 북마크, 댓글, 친구 목록을 한눈에 확인할 수 있습니다.', '새 쪽지가 도착하면 프로필 이미지와 메뉴에 배지가 표시됩니다. 읽은 쪽지는 받은 쪽지함에서 다시 확인할 수 있습니다.'],
  },
  {
    id: 'privacy-2026-08',
    category: '안내',
    title: '개인정보 처리방침 안내',
    summary: 'FAN HEAT의 개인정보 보호 원칙과 이용자 권리를 안내합니다.',
    publishedAt: '2026. 8. 20.',
    body: ['FAN HEAT은 서비스 제공에 필요한 범위에서만 개인정보를 처리하며, 관련 법령과 내부 기준에 따라 안전하게 보호합니다.', '자세한 내용은 프로필 메뉴의 개인정보 처리방침에서 확인하실 수 있습니다.'],
  },
]

function dailyVoteTimeRemaining(now = Date.now()) {
  const koreaOffset = 9 * 60 * 60 * 1000
  const koreaNow = new Date(now + koreaOffset)
  const nextMidnight = Date.UTC(koreaNow.getUTCFullYear(), koreaNow.getUTCMonth(), koreaNow.getUTCDate() + 1) - koreaOffset
  const remaining = Math.max(0, nextMidnight - now)
  const hours = Math.floor(remaining / 3_600_000)
  const minutes = Math.floor((remaining % 3_600_000) / 60_000)
  const seconds = Math.floor((remaining % 60_000) / 1000)
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

function ChartPanel({ onPlay, activeSong, songPlaying = false, items = [], artists = [], collapsed, onToggle, user, onLogin, initialVoteMode = false, dedicatedVotePage = false }) {
  const { t, localizeTitle } = useI18n()
  const [voteMode, setVoteMode] = useState(initialVoteMode)
  const [voteQuery, setVoteQuery] = useState('')
  const [selectedVote, setSelectedVote] = useState(null)
  const [dailyCounts, setDailyCounts] = useState({})
  const [ownVote, setOwnVote] = useState(null)
  const [votePending, setVotePending] = useState(false)
  const [voteMessage, setVoteMessage] = useState('')
  const [voteRemaining, setVoteRemaining] = useState(() => dailyVoteTimeRemaining())
  useEffect(() => {
    let active = true
    loadDailyArtistVotes(user?.id).then(({ counts, ownVote: voted }) => {
      if (!active) return
      setDailyCounts(counts)
      setOwnVote(voted)
    }).catch(error => { if (active) setVoteMessage(error.message) })
    return () => { active = false }
  }, [user?.id])
  useEffect(() => {
    if (!dedicatedVotePage && !voteMode) return undefined
    const update = () => setVoteRemaining(dailyVoteTimeRemaining())
    update()
    const timer = window.setInterval(update, 1000)
    return () => window.clearInterval(timer)
  }, [dedicatedVotePage, voteMode])
  useEffect(() => {
    if (voteMode && collapsed) onToggle?.()
  }, [voteMode, collapsed, onToggle])
  const openVoting = () => {
    if (!user) { onLogin(); return }
    setVoteMode(value => !value); setSelectedVote(null); setVoteQuery(''); setVoteMessage('')
  }
  // The right panel is the daily artist ranking in every state. Voting mode
  // only adds selection controls; it must not swap an unrelated track list in.
  const showVoteRanking = true
  const showVoteScore = voteMode || dedicatedVotePage
  const ownVoteItem = ownVote ? items.find(([, , , data = {}]) => data.artist_id === ownVote.artist_id) : null
  const ownVoteArtist = ownVote ? artists.find(artist => artist.id === ownVote.artist_id) : null
  const ownVoteLabel = ownVoteArtist?.name_ko || ownVoteArtist?.name || ownVoteItem?.[1] || ownVoteItem?.[0] || '선택한 아티스트'
  const artistVoteItems = artists.slice(0, 50).map((artist, index) => [
    artist.name_ko || artist.name,
    artist.name,
    artist.image_url,
    { artist_id: artist.id, display_order: index + 1 },
  ])
  const filteredVoteItems = showVoteRanking
    ? artistVoteItems.filter(([title, artist]) => !voteQuery.trim() || `${title} ${artist}`.toLowerCase().includes(voteQuery.trim().toLowerCase()))
    : items
  const voteScore = ([, , , data = {}]) => Number(dailyCounts[data.artist_id] ?? data.vote_count ?? 0)
  const voteEntries = filteredVoteItems
    .map((item, registrationIndex) => {
      const displayOrder = Number(item[3]?.display_order)
      return { item, registrationIndex, registrationOrder: Number.isFinite(displayOrder) ? displayOrder : registrationIndex, score: voteScore(item) }
    })
    .sort((a, b) => showVoteRanking
      ? b.score - a.score || a.registrationOrder - b.registrationOrder || a.registrationIndex - b.registrationIndex
      : a.registrationOrder - b.registrationOrder || a.registrationIndex - b.registrationIndex)
    .map((entry, position, orderedEntries) => {
      const previous = orderedEntries[position - 1]
      const previousRank = previous?.rankNumber || 1
      entry.rankNumber = showVoteRanking
        ? position && entry.score === previous.score ? previousRank : position ? previousRank + 1 : 1
        : Number(entry.item[3]?.display_order) || position + 1
      return entry
    })
  const voteUnchanged = Boolean(selectedVote && ownVote?.artist_id === selectedVote.data.artist_id)
  const submitVote = async () => {
    if (!selectedVote || !user || voteUnchanged) return
    setVotePending(true); setVoteMessage('')
    try { const result = await castDailyArtistVote(user.id, selectedVote.data.artist_id); setDailyCounts(result.counts); setOwnVote(result.ownVote); setSelectedVote(null); setVoteMode(false) }
    catch (error) { setVoteMessage(error.message) }
    finally { setVotePending(false) }
  }
  return <aside className={`chart-panel ${collapsed ? 'collapsed' : ''} ${voteMode ? 'voting-mode' : ''}`.trim()}>
    <div className="brand-tile">
      <button className="back-button" onClick={onToggle} aria-label={collapsed ? '순위 목록 펼치기' : '순위 목록 접기'} aria-expanded={!collapsed}><span>{collapsed ? '→' : '←'}</span></button>
      <img src={`${A}fanheat-logo.png`} alt="FAN HEAT" />
      <span className="brand-tagline">Where Human &amp; AI<br />Fandom Connect</span>
      {voteMode && <button className="vote-mode-close" type="button" onClick={openVoting} aria-label="투표 취소"><span aria-hidden="true">×</span><b>취소</b></button>}
      <div className="mobile-vote-intro"><small>FAN HEAT DAILY PICK</small><strong>오늘 가장 빛나는 아티스트를 선택하세요</strong></div>
      {voteMode && <div className="vote-mode-controls"><div className="daily-vote-countdown"><small>오늘 투표 마감까지</small><strong>{voteRemaining}</strong></div><label className="vote-search"><input value={voteQuery} onChange={event => setVoteQuery(event.target.value)} placeholder="가수 검색" autoFocus={!ownVote} /><span>⌕</span></label></div>}
      {dedicatedVotePage && !voteMode && <p className={`daily-vote-state ${ownVote ? 'complete' : ''}`}>{ownVote ? `오늘의 선택 · ${localizeTitle(ownVoteLabel)}` : '오늘 아직 투표하지 않았어요'}</p>}
      {!voteMode && <button className={`vote-button ${ownVote ? 'complete' : ''}`} onClick={openVoting}>{ownVote ? '1Day 투표 완료' : t('voteDay')}</button>}
    </div>
    <ol className={`chart-list ${showVoteRanking ? 'voting vote-ranking' : ''} ${showVoteScore ? 'score-visible' : ''} ${dedicatedVotePage && !voteMode ? 'vote-readonly' : ''}`}>
      {voteEntries.map(({ item: [title, artist, image, data = {}], score, rankNumber }, index) => {
        const crownCount = dedicatedVotePage && rankNumber && rankNumber <= 3 ? 4 - rankNumber : 0
        const selected = voteMode ? (selectedVote?.data.artist_id || ownVote?.artist_id) === data.artist_id : false
        return <li key={`${data.artist_id || title}-${index}`} className={`${USER_MUSIC_PLAYBACK_ENABLED && activeSong === index && !showVoteRanking ? 'playing' : ''} ${selected ? 'vote-selected' : ''}`.trim()}>
        <button type="button" onClick={() => voteMode ? setSelectedVote({ title, artist, image, data }) : dedicatedVotePage || !USER_MUSIC_PLAYBACK_ENABLED ? undefined : onPlay(index)} aria-label={voteMode ? ownVote?.artist_id === data.artist_id ? `${title}, 현재 투표한 아티스트` : `${title}로 투표 변경` : dedicatedVotePage ? `${rankNumber ? `${rankNumber}위` : '순위 미정'} ${title}, 현재 ${score.toLocaleString()}표` : `${rankNumber}위 ${title}, ${artist}`}>
          <span className={`rank ${rankNumber ? `vote-rank-${rankNumber}` : 'vote-unranked'}`}>
            {crownCount > 0 && <span className="rank-crowns" aria-hidden="true">{Array.from({ length: crownCount }, (_, crownIndex) => <span key={crownIndex}>👑</span>)}</span>}
            <span>{rankNumber ? String(rankNumber).padStart(2, '0') : '—'}</span>
          </span>
          <span className="cover"><img src={assetSrc(image)} alt={`${title} 커버`} /><b className={`compact-rank rank-${index + 1}`}>{index + 1}위</b>{USER_MUSIC_PLAYBACK_ENABLED && <i>{activeSong === index && songPlaying ? 'Ⅱ' : '▶'}</i>}</span>
          <span className="song"><strong>{localizeTitle(title)}</strong><small>{artist}</small></span>
          {showVoteScore && <span className="vote-score"><small>SCORE</small><strong>{score.toLocaleString()}</strong></span>}
          {voteMode && <span className={`vote-check ${selected ? 'selected' : ''}`}>✓</span>}
        </button>
      </li>})}
      {voteMode && selectedVote && <div className="vote-confirm" role="dialog" aria-modal="true" aria-label="가수 투표 확인"><img src={assetSrc(selectedVote.image)} alt="" /><h3>{selectedVote.title}</h3><p>{selectedVote.artist}</p><span>Today</span><strong>{(dailyCounts[selectedVote.data.artist_id] || 0).toLocaleString()}<small>표</small></strong>{voteMessage && <em>{voteMessage}</em>}<div><button onClick={submitVote} disabled={votePending || voteUnchanged}>{voteUnchanged ? '현재 선택' : votePending ? '처리 중' : ownVote ? '변경' : '투표'}</button><button onClick={() => setSelectedVote(null)}>취소</button></div></div>}
    </ol>
    {voteMode && <div className="vote-cancel-bar"><button type="button" onClick={openVoting}>투표 취소</button></div>}
  </aside>
}

function MobileVotePage({ onClose, ...chartProps }) {
  return <section className="mobile-vote-page mobile-vote-sheet" aria-labelledby="mobile-vote-title">
    <header><button className="mobile-vote-page-back" type="button" onClick={onClose} aria-label="홈으로 돌아가기">‹</button><div><small>DAILY VOTE</small><h2 id="mobile-vote-title">오늘의 아티스트 투표</h2></div></header>
    <ChartPanel {...chartProps} dedicatedVotePage collapsed={false} onToggle={onClose} />
  </section>
}

function Hero({ user, onLogin, slides: configuredSlides = [] }) {
  const slides = configuredSlides
  const [active, setActive] = useState(0)
  const [paused, setPaused] = useState(false)
  const [photoOpen, setPhotoOpen] = useState(false)
  const [photoNote, setPhotoNote] = useState('')
  const [photoFiles, setPhotoFiles] = useState([])
  const [photoConsent, setPhotoConsent] = useState(false)
  const [photoStatus, setPhotoStatus] = useState('')
  const [photoSubmitting, setPhotoSubmitting] = useState(false)
  useEffect(() => { if (active >= slides.length) setActive(0) }, [active, slides.length])
  useEffect(() => {
    if (paused || slides.length < 2) return undefined
    const timer = setInterval(() => setActive(current => (current + 1) % slides.length), 5000)
    return () => clearInterval(timer)
  }, [paused, slides.length])
  useEffect(() => {
    if (!photoOpen) return undefined
    const previousOverflow = document.body.style.overflow
    const closeOnEscape = event => event.key === 'Escape' && setPhotoOpen(false)
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [photoOpen])
  useEffect(() => {
    const openFanPhoto = () => {
      window.sessionStorage.removeItem('fanheat:open-fan-photo')
      setPhotoStatus('')
      setPhotoOpen(true)
    }
    window.addEventListener('fanheat:open-fan-photo', openFanPhoto)
    if (window.sessionStorage.getItem('fanheat:open-fan-photo') === 'pending') openFanPhoto()
    return () => window.removeEventListener('fanheat:open-fan-photo', openFanPhoto)
  }, [])
  const addFanPhotos = async event => {
    const selected = [...event.target.files].slice(0, Math.max(0, 5 - photoFiles.length))
    event.target.value = ''
    const allowed = selected.filter(file => ['image/jpeg', 'image/png', 'image/webp'].includes(file.type) && file.size <= 25 * 1024 * 1024)
    if (allowed.length !== selected.length) setPhotoStatus('JPG, PNG, WebP 형식과 장당 25MB 이하의 이미지만 추가할 수 있습니다.')
    const measured = await Promise.all(allowed.map(file => new Promise(resolve => {
      const preview = URL.createObjectURL(file)
      const image = new window.Image()
      image.onload = () => resolve({ file, preview, width: image.naturalWidth, height: image.naturalHeight })
      image.onerror = () => { URL.revokeObjectURL(preview); resolve(null) }
      image.src = preview
    })))
    setPhotoFiles(current => [...current, ...measured.filter(Boolean)].slice(0, 5))
  }
  const removeFanPhoto = index => setPhotoFiles(current => {
    URL.revokeObjectURL(current[index].preview)
    return current.filter((_, itemIndex) => itemIndex !== index)
  })
  const submitFanPhotoShare = async event => {
    event.preventDefault()
    if (!user) { onLogin(); return }
    if (!photoFiles.length || !photoConsent) return
    setPhotoSubmitting(true); setPhotoStatus('')
    try {
      await submitFanPhotos(photoFiles, photoNote, user)
      photoFiles.forEach(item => URL.revokeObjectURL(item.preview))
      setPhotoFiles([]); setPhotoNote(''); setPhotoConsent(false)
      setPhotoStatus('사진이 접수되었습니다. 운영진 검토 후 배경 이미지로 선정될 수 있습니다.')
    } catch (error) { setPhotoStatus(`접수하지 못했습니다: ${error.message}`) }
    finally { setPhotoSubmitting(false) }
  }
  return <section className="hero" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
    <div className="hero-backgrounds" aria-hidden="true">{slides.map((slide, index) => <div key={slide.id || slide.background_url} className={active === index ? 'active' : ''} style={{ backgroundImage: `linear-gradient(135deg,rgba(101,44,148,.76),rgba(16,143,219,.78)),url(${assetSrc(slide.background_url)})` }} />)}</div>
    <div className="hero-carousel">
      <div className="hero-track" style={{ transform: `translate3d(-${active * 100}%,0,0)` }}>{slides.map(slide => <article className={`album-card ${slide.layout_type === 'background' ? 'background-only' : ''}`} key={slide.id || slide.background_url}>
        {slide.layout_type !== 'background' && slide.foreground_url && <img src={assetSrc(slide.foreground_url)} alt={slide.title} />}
        {(slide.title || slide.subtitle) && <p><strong>{slide.title}</strong><span>{slide.subtitle}</span></p>}
      </article>)}</div>
      <div className="hero-dots">{slides.map((_, index) => <button key={index} className={active === index ? 'active' : ''} onClick={() => setActive(index)} aria-label={`${index + 1}번째 재킷`} />)}</div>
    </div>
    <button className="ad-request-button" type="button" onClick={() => { setPhotoStatus(''); setPhotoOpen(true) }}>팬 사진 공유 <span aria-hidden="true">↗</span></button>
    {photoOpen && createPortal(<div className="ad-inquiry-overlay" role="presentation" onMouseDown={event => event.target === event.currentTarget && setPhotoOpen(false)}><section className="ad-inquiry-modal fan-photo-modal" role="dialog" aria-modal="true" aria-labelledby="fan-photo-title"><header><div><small>FAN PHOTO SHARE</small><h2 id="fan-photo-title">팬 사진 공유</h2><p>직접 촬영한 사진을 FANHEAT 배경 후보로 공유해 주세요.</p></div><button type="button" onClick={() => setPhotoOpen(false)} aria-label="팬 사진 공유 닫기">×</button></header><div className="fan-photo-guide"><strong>무료 사진 공유 안내</strong><p>비용 없이 접수되며, 선정된 사진은 메인 배경으로 사용될 수 있습니다.</p><dl><div><dt>권장</dt><dd>2560 × 1440 이상</dd></div><div><dt>최소</dt><dd>1920 × 1080</dd></div><div><dt>비율</dt><dd>가로 16:9</dd></div><div><dt>파일</dt><dd>JPG · PNG · WebP</dd></div></dl></div><form onSubmit={submitFanPhotoShare}><label><span>사진 설명 <small>선택</small></span><textarea value={photoNote} onChange={event => setPhotoNote(event.target.value)} maxLength="500" placeholder="촬영 대상 · 날짜 · 장소 · 상황을 적어주세요." /></label><div className="fan-photo-upload"><label><input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={addFanPhotos} disabled={photoFiles.length >= 5 || photoSubmitting} /><b>＋ 사진 선택</b><span>{photoFiles.length} / 5장</span></label><p className="fan-photo-upload-help">{photoFiles.length ? `${photoFiles.length}장 선택됨 · ${5 - photoFiles.length}장 더 추가 가능` : '한 번에 여러 장, 최대 5장까지 선택할 수 있습니다.'}</p><div>{photoFiles.map((item, index) => <figure key={item.preview}><img src={item.preview} alt={`${index + 1}번째 공유 사진`} /><figcaption>{item.width}×{item.height}<small>{item.width < 1920 || item.height < 1080 ? '권장 규격 미달' : `${(item.file.size / 1024 / 1024).toFixed(1)}MB`}</small></figcaption><button type="button" onClick={() => removeFanPhoto(index)} aria-label={`${index + 1}번째 사진 삭제`}>×</button></figure>)}</div></div><label className="fan-photo-consent"><input type="checkbox" checked={photoConsent} onChange={event => setPhotoConsent(event.target.checked)} required /><span>사진의 권리를 보유하고 있으며, 운영진 심사 후 FANHEAT 배경 이미지로 무상 사용하는 것에 동의합니다.</span></label>{photoStatus && <p className="fan-photo-status" role="status">{photoStatus}</p>}<button type="submit" disabled={!photoFiles.length || !photoConsent || photoSubmitting}>{!user ? '로그인하고 공유하기' : photoSubmitting ? '사진 업로드 중…' : `${photoFiles.length}장 공유하기`}</button></form><p className="ad-mail-note"><span aria-hidden="true">✓</span> 제출된 사진은 이메일이 아닌 FANHEAT 관리자 검토함에 안전하게 접수됩니다.</p></section></div>, document.body)}
  </section>
}

function SharedHeader({ query, setQuery, trendingKeywords = [], menuOpen, setMenuOpen, loggedIn, user, unreadMessageCount = 0, onLogin, onWrite, onHome, onMyPage, onLogout, writing, searchFilters, setSearchFilters, filterAuthors = [] }) {
  const { locale, setLocale, t } = useI18n()
  const [profileOpen, setProfileOpen] = useState(false)
  const [filterOpen, setFilterOpen] = useState(false)
  const [noticeOpen, setNoticeOpen] = useState(false)
  const [selectedNotice, setSelectedNotice] = useState(null)
  const noticeStorageKey = `fanheat:read-notices:${user?.id || 'guest'}`
  const [readNoticeIds, setReadNoticeIds] = useState(() => {
    try { return JSON.parse(window.localStorage.getItem(noticeStorageKey) || '[]') }
    catch { return [] }
  })
  const profileMenu = useRef(null)
  const filterMenu = useRef(null)
  useEffect(() => {
    const close = event => { if (!profileMenu.current?.contains(event.target)) setProfileOpen(false) }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [])
  useEffect(() => {
    const close = event => { if (!filterMenu.current?.contains(event.target)) setFilterOpen(false) }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [])
  useEffect(() => {
    if (!menuOpen || !window.matchMedia('(max-width: 700px)').matches) return undefined
    const previousOverflow = document.body.style.overflow
    const closeOnEscape = event => { if (event.key === 'Escape') setMenuOpen(false) }
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [menuOpen, setMenuOpen])
  useEffect(() => {
    try { setReadNoticeIds(JSON.parse(window.localStorage.getItem(noticeStorageKey) || '[]')) }
    catch { setReadNoticeIds([]) }
  }, [noticeStorageKey])
  useEffect(() => {
    if (!noticeOpen) return undefined
    const previousOverflow = document.body.style.overflow
    const closeOnEscape = event => {
      if (event.key !== 'Escape') return
      if (selectedNotice) setSelectedNotice(null)
      else setNoticeOpen(false)
    }
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', closeOnEscape)
    return () => { document.body.style.overflow = previousOverflow; window.removeEventListener('keydown', closeOnEscape) }
  }, [noticeOpen, selectedNotice])
  const displayName = user?.user_metadata?.display_name || user?.email?.split('@')[0] || 'FAN'
  const showFilters = !writing
  const activeFilterCount = showFilters ? Number(Boolean(searchFilters?.from)) + Number(Boolean(searchFilters?.to)) + Number(searchFilters?.author !== 'all') + Number(searchFilters?.sort !== 'latest') : 0
  const updateFilter = (key, value) => setSearchFilters(current => ({ ...current, [key]: value }))
  const openDatePicker = event => {
    try { event.currentTarget.showPicker?.() } catch { event.currentTarget.focus() }
  }
  const openInfoPage = path => { setProfileOpen(false); setMenuOpen(false); window.open(`${window.location.origin}${path}?lang=${locale}`, '_blank', 'noopener,noreferrer') }
  const openMobileFeed = sort => { setSearchFilters(current => ({ ...current, sort })); setMenuOpen(false); onHome() }
  const selectKeyword = keyword => {
    setQuery(keyword)
    setMenuOpen(false)
    onHome()
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => document.getElementById('feed')?.scrollIntoView({ behavior: 'smooth', block: 'start' })))
  }
  const openFanPhotoShare = () => {
    window.sessionStorage.setItem('fanheat:open-fan-photo', 'pending')
    setMenuOpen(false)
    onHome()
    window.requestAnimationFrame(() => window.dispatchEvent(new CustomEvent('fanheat:open-fan-photo')))
  }
  const unreadNoticeCount = serviceNotices.filter(notice => !readNoticeIds.includes(notice.id)).length
  const openNotices = () => { setProfileOpen(false); setMenuOpen(false); setSelectedNotice(null); setNoticeOpen(true) }
  const openCopyrightReport = () => { setProfileOpen(false); setMenuOpen(false); window.dispatchEvent(new CustomEvent('fanheat:open-copyright-report')) }
  const openNoticeDetail = notice => {
    setSelectedNotice(notice)
    if (readNoticeIds.includes(notice.id)) return
    const next = [...readNoticeIds, notice.id]
    setReadNoticeIds(next)
    window.localStorage.setItem(noticeStorageKey, JSON.stringify(next))
  }
  const noticeLayer = noticeOpen && createPortal(<div className="notice-overlay" role="presentation" onMouseDown={event => event.target === event.currentTarget && setNoticeOpen(false)}>
    <section className="notice-center" role="dialog" aria-modal="true" aria-labelledby="notice-title">
      <header><button type="button" className="notice-back" onClick={() => setSelectedNotice(null)} aria-label="공지사항 목록으로 돌아가기">‹</button><div><small>FAN HEAT NEWS</small><h2 id="notice-title">{selectedNotice ? '공지사항 상세' : '공지사항'}</h2></div><button type="button" className="notice-close" onClick={() => setNoticeOpen(false)} aria-label="공지사항 닫기">×</button></header>
      {selectedNotice ? <article className="notice-detail"><div className="notice-detail-meta"><span>{selectedNotice.category}</span><time>{selectedNotice.publishedAt}</time></div><h3>{selectedNotice.title}</h3><p className="notice-detail-summary">{selectedNotice.summary}</p><div className="notice-detail-body">{selectedNotice.body.map(paragraph => <p key={paragraph}>{paragraph}</p>)}</div><button type="button" onClick={() => setSelectedNotice(null)}>목록으로</button></article> : <div className="notice-list" role="list">{serviceNotices.map(notice => { const unread = !readNoticeIds.includes(notice.id); return <button type="button" className={unread ? 'unread' : ''} onClick={() => openNoticeDetail(notice)} role="listitem" key={notice.id}><span className="notice-list-copy"><span className="notice-list-meta"><em>{notice.category}</em>{unread && <i>NEW</i>}</span><strong>{notice.title}</strong></span><span className="notice-list-action"><time>{notice.publishedAt}</time><b aria-hidden="true">›</b></span></button> })}</div>}
    </section>
  </div>, document.body)
  return <header className="topbar">
    <div className="mobile-header-main">
      <button className="mobile-header-menu" type="button" onClick={() => setMenuOpen(value => !value)} aria-expanded={menuOpen} aria-label={menuOpen ? '메뉴 닫기' : '메뉴 열기'}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg></button>
    </div>
    <a className="mobile-logo" href="#top" onClick={onHome} aria-label="FAN HEAT 홈">
      <img className="header-brand-image" src={`${A}fanheat-logo.png`} alt="FAN HEAT" />
    </a>
    <div className="header-search-tools" ref={filterMenu}><form className="search" onSubmit={e => e.preventDefault()}><span className="desktop-search-icon">⌕</span><img className="mobile-search-star" src={`${A}fanheat-logo.png`} alt="" /><input value={query} onInput={event => setQuery(event.currentTarget.value)} placeholder={t('search')} aria-label={t('search')} /></form>{showFilters && <><button className={`search-filter-button ${activeFilterCount ? 'active' : ''}`} type="button" onClick={() => setFilterOpen(value => !value)} aria-expanded={filterOpen}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4" /></svg><span>필터</span>{activeFilterCount > 0 && <b>{activeFilterCount}</b>}</button>{filterOpen && <section className="search-filter-popover" aria-label="게시글 검색 필터"><header><div><small>SEARCH FILTER</small><strong>게시글 필터</strong></div><button type="button" onClick={() => setSearchFilters({ from: '', to: '', author: 'all', sort: 'latest' })}>초기화</button></header><div className="filter-date-row"><label><span>시작일</span><input type="date" value={searchFilters.from} onClick={openDatePicker} onChange={event => updateFilter('from', event.target.value)} aria-label="검색 시작일" /></label><label><span>종료일</span><input type="date" value={searchFilters.to} onClick={openDatePicker} onChange={event => updateFilter('to', event.target.value)} aria-label="검색 종료일" /></label></div><label><span>작성자</span><select value={searchFilters.author} onChange={event => updateFilter('author', event.target.value)}><option value="all">전체 사용자</option>{filterAuthors.map(author => <option value={author} key={author}>@{author.replace(/^@/, '')}</option>)}</select></label><label><span>정렬</span><select value={searchFilters.sort} onChange={event => updateFilter('sort', event.target.value)}><option value="latest">최신 글 순</option><option value="popular">HEAT 인기순</option><option value="comments">댓글 많은 순</option></select></label><button className="filter-apply" type="button" onClick={() => setFilterOpen(false)}>필터 적용</button></section>}</>}</div>
    {trendingKeywords.length > 0 && <div className="keywords" aria-label="인기 키워드"><span aria-hidden="true">›</span>{trendingKeywords.map(keyword => <button type="button" key={keyword} className={query.trim().toLocaleLowerCase('ko-KR') === keyword.toLocaleLowerCase('ko-KR') ? 'active' : ''} aria-pressed={query.trim().toLocaleLowerCase('ko-KR') === keyword.toLocaleLowerCase('ko-KR')} onClick={() => selectKeyword(keyword)}>#{keyword}</button>)}</div>}
    <nav className={menuOpen ? 'open' : ''}>
      <label className="language-picker" aria-label={t('language')}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.7 2.5 4 5.5 4 9s-1.3 6.5-4 9c-2.7-2.5-4-5.5-4-9s1.3-6.5 4-9Z"/></svg><select value={locale} onChange={event => setLocale(event.target.value)}><option value="ko">🇰🇷 KO</option><option value="en">🇺🇸 EN</option><option value="ja">🇯🇵 JPN</option></select></label>
      {loggedIn ? <div className="profile-actions">
        <button className={`write-button ${writing ? 'active' : ''}`} onClick={onWrite}>{writing ? t('writing') : t('write')}</button>
        <div className="profile-menu-wrap" ref={profileMenu}>
          <button className="profile-button" onClick={() => setProfileOpen(value => !value)} aria-expanded={profileOpen} aria-haspopup="menu" aria-label={`프로필 퀵 메뉴${unreadMessageCount ? `, 읽지 않은 쪽지 ${unreadMessageCount}건` : ''}`}><img src={assetSrc(user?.user_metadata?.avatar_url || 'mypage.jpg')} alt="" />{unreadMessageCount > 0 && <i>{unreadMessageCount > 99 ? '99+' : unreadMessageCount}</i>}</button>
          {profileOpen && <div className="profile-quick-menu profile-account-menu" role="menu">
            <p className="profile-menu-caption">현재 로그인 계정</p>
            <header><img src={assetSrc(user?.user_metadata?.avatar_url || 'mypage.jpg')} alt="" /><strong>{displayName}</strong></header>
            <section><h3>내 계정</h3><button role="menuitem" onClick={() => { setProfileOpen(false); onMyPage('posts') }}>마이 페이지</button><button role="menuitem" onClick={() => { setProfileOpen(false); onMyPage('followers') }}>내 친구</button><button role="menuitem" onClick={() => { setProfileOpen(false); onMyPage('messages') }}>쪽지 <b>{unreadMessageCount > 0 ? `${unreadMessageCount} NEW` : '›'}</b></button></section>
            <section><h3>콘텐츠</h3><button role="menuitem" onClick={() => { setProfileOpen(false); onWrite() }}>글 작성</button><button role="menuitem" onClick={() => { setProfileOpen(false); onMyPage('bookmarks') }}>북마크</button><button role="menuitem" onClick={() => { setProfileOpen(false); onMyPage('posts') }}>포스트</button></section>
            <section><h3>안내</h3><button role="menuitem" onClick={openNotices}>공지사항 {unreadNoticeCount > 0 ? <b className="notice-menu-badge">{unreadNoticeCount} NEW</b> : <b aria-hidden="true">›</b>}</button><button role="menuitem" onClick={openCopyrightReport}>저작권 신고 <b aria-hidden="true">›</b></button><button role="menuitem" onClick={() => openInfoPage('/legal/terms')}>서비스 이용약관 <b aria-hidden="true">↗</b></button><button role="menuitem" onClick={() => openInfoPage('/legal/privacy')}>개인정보 처리방침 <b aria-hidden="true">↗</b></button><button role="menuitem" onClick={() => openInfoPage('/support')}>고객지원 <b aria-hidden="true">↗</b></button></section>
            <button className="quick-logout" role="menuitem" onClick={() => { setProfileOpen(false); onLogout() }}>로그아웃</button>
          </div>}
        </div>
      </div> : <button className="login" onClick={onLogin}>{t('login')}</button>}
    </nav>
    {menuOpen && <div className="mobile-menu-overlay" role="presentation" onMouseDown={event => event.target === event.currentTarget && setMenuOpen(false)}><aside className="mobile-menu-drawer" role="dialog" aria-modal="true" aria-labelledby="mobile-menu-title"><header><div><small>FAN HEAT</small><h2 id="mobile-menu-title">메뉴</h2></div><button type="button" onClick={() => setMenuOpen(false)} aria-label="메뉴 닫기">×</button></header><nav aria-label="모바일 전체 메뉴"><section><h3>콘텐츠 탐색</h3><button type="button" className={searchFilters?.sort === 'popular' ? 'active' : ''} onClick={() => openMobileFeed('popular')}><span aria-hidden="true">↗</span><b>인기</b><small>HEAT가 높은 포스트</small></button><button type="button" className={searchFilters?.sort === 'latest' ? 'active' : ''} onClick={() => openMobileFeed('latest')}><span aria-hidden="true">◷</span><b>최신</b><small>최근 등록된 포스트</small></button></section><section><h3>팬 참여</h3><button type="button" onClick={openFanPhotoShare}><span aria-hidden="true">▧</span><b>팬 사진 공유</b><small>직접 촬영한 사진 보내기</small></button></section><section className="mobile-menu-language"><h3>언어</h3><div>{[['ko','한국어'],['ja','日本語'],['en','English']].map(([value, label]) => <button type="button" className={locale === value ? 'active' : ''} onClick={() => { setLocale(value); setMenuOpen(false) }} aria-pressed={locale === value} key={value}>{label}</button>)}</div></section><section><h3>서비스 안내</h3><button type="button" onClick={openNotices}><b>공지사항</b>{unreadNoticeCount > 0 ? <em className="mobile-notice-badge">{unreadNoticeCount} NEW</em> : <span aria-hidden="true">›</span>}</button><button type="button" onClick={() => openInfoPage('/legal/terms')}><b>서비스 이용약관</b><span aria-hidden="true">›</span></button><button type="button" onClick={() => openInfoPage('/legal/privacy')}><b>개인정보 처리방침</b><span aria-hidden="true">›</span></button><button type="button" onClick={() => openInfoPage('/support')}><b>고객지원</b><span aria-hidden="true">›</span></button></section></nav></aside></div>}
    <button className="menu-button" onClick={() => setMenuOpen(v => !v)} aria-expanded={menuOpen} aria-label="메뉴 열기">{menuOpen ? '×' : '☰'}</button>
    {noticeLayer}
    <CopyrightReportDialog user={user} />
  </header>
}

const formatAudioTime = value => `${Math.floor((Number.isFinite(value) ? value : 0) / 60)}:${String(Math.floor((Number.isFinite(value) ? value : 0) % 60)).padStart(2, '0')}`

function UnifiedAudioPlayer({ track, playing, onPlayingChange, onPrevious, onNext, onOpenPlaylist, className = '', label = '음원 플레이어' }) {
  const audio = useRef(null)
  const [muted, setMuted] = useState(false)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState(0)
  const audioUrl = track?.audioUrl || '/sample.mp3'
  useEffect(() => {
    const node = audio.current
    if (!node) return
    node.load()
    setProgress(0)
    setDuration(0)
  }, [audioUrl, track?.id])
  useEffect(() => {
    const node = audio.current
    if (!node) return
    if (playing && node.paused) node.play().catch(() => onPlayingChange(false))
    if (!playing && !node.paused) node.pause()
  }, [playing, audioUrl, track?.id])
  useEffect(() => {
    if (!playing) return undefined
    let frame
    const syncProgress = () => {
      const node = audio.current
      if (node) {
        setProgress(node.currentTime || 0)
        if (Number.isFinite(node.duration) && node.duration > 0) setDuration(node.duration)
      }
      frame = window.requestAnimationFrame(syncProgress)
    }
    frame = window.requestAnimationFrame(syncProgress)
    return () => window.cancelAnimationFrame(frame)
  }, [playing, audioUrl, track?.id])
  if (!USER_MUSIC_PLAYBACK_ENABLED) return null
  const toggle = () => {
    const node = audio.current
    if (!node) return
    if (node.paused) node.play().then(() => onPlayingChange(true)).catch(() => onPlayingChange(false))
    else { node.pause(); onPlayingChange(false) }
  }
  const restart = () => {
    if (!audio.current) return
    audio.current.currentTime = 0
    setProgress(0)
  }
  const toggleMute = () => {
    if (!audio.current) return
    audio.current.muted = !audio.current.muted
    setMuted(audio.current.muted)
  }
  const seek = event => {
    const nextTime = Number(event.target.value)
    if (!audio.current || !Number.isFinite(nextTime)) return
    audio.current.currentTime = nextTime
    setProgress(nextTime)
  }
  const seekFromPointer = event => {
    if (!audio.current || !duration) return
    const bounds = event.currentTarget.getBoundingClientRect()
    const ratio = Math.max(0, Math.min(1, (event.clientX - bounds.left) / Math.max(1, bounds.width)))
    const nextTime = ratio * duration
    audio.current.currentTime = nextTime
    setProgress(nextTime)
  }
  return <section className={`detail-audio unified-audio-player ${className}`.trim()} aria-label={label}>
    <audio ref={audio} src={audioUrl} muted={muted} onTimeUpdate={event => setProgress(event.currentTarget.currentTime)} onLoadedMetadata={event => setDuration(Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0)} onEnded={() => onNext ? onNext() : onPlayingChange(false)} />
    <button className="audio-play" type="button" onClick={toggle} aria-label={playing ? '음원 일시정지' : '음원 재생'}>{playing ? 'Ⅱ' : '▶'}</button>
    <button className="audio-skip" type="button" onClick={() => progress > 3 || !onPrevious ? restart() : onPrevious()} aria-label="이전 곡">◀</button>
    <button className="audio-skip" type="button" onClick={() => onNext ? onNext() : restart()} aria-label="다음 곡">▶</button>
    <button className="audio-volume" type="button" onClick={toggleMute} aria-label={muted ? '음소거 해제' : '음소거'}><img src={`${A}${muted ? 'volume_off.png' : 'volume_up.png'}`} alt="" /></button>
    <a className="audio-download" href={audioUrl} download aria-label="음원 다운로드">⬇</a>
    <img src={assetSrc(track?.cover || 'music1.jpg')} alt="" />
    <div className={`audio-info ${playing ? 'is-playing' : ''}`} style={{ '--audio-progress': `${duration ? Math.min(100, progress / duration * 100) : 0}%` }} onPointerDown={event => { if (event.button !== 0) return; seekFromPointer(event); event.currentTarget.setPointerCapture?.(event.pointerId) }} onPointerMove={event => event.currentTarget.hasPointerCapture?.(event.pointerId) && seekFromPointer(event)} onPointerUp={event => event.currentTarget.releasePointerCapture?.(event.pointerId)}><b>{track?.title || 'FANHEAT MUSIC'}</b><span>{track?.artist || '아티스트 정보 없음'}</span><input className="audio-seek" type="range" min="0" max={duration || 0} step="0.1" value={Math.min(progress, duration || 0)} onInput={seek} onChange={seek} aria-label="음원 재생 위치" aria-valuetext={`${formatAudioTime(progress)} / ${formatAudioTime(duration)}`} /></div>
    <time className="audio-time"><span>{formatAudioTime(progress)}</span><span>{formatAudioTime(duration)}</span></time>
    <button className="audio-menu" type="button" onClick={onOpenPlaylist || (() => {})} aria-label="재생목록">☰</button>
  </section>
}

function MyPageAudioPlayer({ track, playing, onPlayingChange, onPrevious, onNext }) {
  if (!USER_MUSIC_PLAYBACK_ENABLED || !track) return null
  return <UnifiedAudioPlayer track={{ id: track[3], cover: track[0], title: track[1], artist: track[2], audioUrl: track[4] }} playing={playing} onPlayingChange={onPlayingChange} onPrevious={onPrevious} onNext={onNext} onOpenPlaylist={() => document.querySelector('.my-music')?.scrollIntoView({ behavior: 'smooth', block: 'center' })} className="my-page-unified-audio" label="마이 뮤직 플레이어" />
}

const emptyProfileSocialDefaults = new Set(['https://www.facebook.com/', 'https://x.com/', 'https://www.instagram.com/'])
const editableProfileSocialUrl = value => emptyProfileSocialDefaults.has(String(value || '').trim()) ? '' : String(value || '').trim()

function ProfileEditPanel({ initial, music, gallery, busy, status, onAddGallery, onRemoveGallery, onClose, onSave }) {
  const [values, setValues] = useState(() => ({
    displayName: initial.display_name || '',
    headline: initial.profile_headline || '',
    bio: initial.bio || '',
    facebookUrl: editableProfileSocialUrl(initial.facebook_url),
    xUrl: editableProfileSocialUrl(initial.x_url),
    instagramUrl: editableProfileSocialUrl(initial.instagram_url),
    tiktokUrl: editableProfileSocialUrl(initial.tiktok_url),
    youtubeUrl: editableProfileSocialUrl(initial.youtube_url),
    favoriteTrackId: initial.favorite_track_id || '',
  }))
  const initialMedia = kind => {
    if (kind === 'cover' && !initial._cover_is_set) return []
    const urls = initial[`${kind}_urls`]?.length ? initial[`${kind}_urls`] : initial[`${kind}_url`] ? [initial[`${kind}_url`]] : []
    const paths = initial[`${kind}_object_paths`]?.length ? initial[`${kind}_object_paths`] : initial[`${kind}_object_path`] ? [initial[`${kind}_object_path`]] : []
    return urls.slice(0, 5).map((url, index) => ({ id: `${kind}-${index}`, url, path: paths[index] || null, preview: url }))
  }
  const [avatarItems, setAvatarItems] = useState(() => initialMedia('avatar'))
  const [coverItems, setCoverItems] = useState(() => initialMedia('cover'))
  const mediaPreviews = useRef(new Set())
  const [saving, setSaving] = useState(false)
  const [saveStatus, setSaveStatus] = useState('')
  useEffect(() => () => mediaPreviews.current.forEach(preview => URL.revokeObjectURL(preview)), [])
  const update = (key, value) => setValues(current => ({ ...current, [key]: value }))
  const chooseImages = (files, items, setter) => {
    const selected = [...files]
    if (!selected.length) return
    if (selected.length > 5 - items.length) { setSaveStatus(`이미지는 최대 5장입니다. 지금은 ${5 - items.length}장 더 추가할 수 있습니다.`); return }
    if (selected.some(file => !['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024)) { setSaveStatus('JPG, PNG, WebP 이미지만 장당 5MB까지 선택할 수 있습니다.'); return }
    setter(current => [...current, ...selected.map(file => { const preview = URL.createObjectURL(file); mediaPreviews.current.add(preview); return { id: crypto.randomUUID(), file, preview } })])
    setSaveStatus('')
  }
  const removeImage = (id, setter) => setter(current => {
    const target = current.find(item => item.id === id)
    if (target?.file) { URL.revokeObjectURL(target.preview); mediaPreviews.current.delete(target.preview) }
    return current.filter(item => item.id !== id)
  })
  const mediaPicker = (items, setter, kind, label) => <div className={`profile-media-strip media-${kind}`}>
    {items.map((item, index) => <figure key={item.id}><img src={item.preview} alt={`${label} ${index + 1} 미리보기`} onError={event => { event.currentTarget.onerror = null; event.currentTarget.src = kind === 'avatar' ? '/images/mypage.jpg' : '/images/auth-concert.jpg'; event.currentTarget.classList.add('is-fallback') }} /><button type="button" onClick={() => removeImage(item.id, setter)} aria-label={`${label} ${index + 1} 삭제`}>×</button></figure>)}
    {items.length < 5 && <label><b>＋</b><span>추가</span><input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={event => { chooseImages(event.target.files, items, setter); event.target.value = '' }} /></label>}
  </div>
  const submit = async event => {
    event.preventDefault()
    setSaving(true)
    setSaveStatus('프로필을 저장하고 있습니다…')
    try { await onSave({ values, avatarItems, coverItems }); setSaveStatus('프로필을 저장했습니다.'); window.setTimeout(onClose, 450) } catch (error) { setSaveStatus(error.message) } finally { setSaving(false) }
  }
  return createPortal(<div className="profile-edit-workspace"><section className="profile-edit-panel" aria-labelledby="profile-edit-title"><header><div><small>MY PROFILE</small><h2 id="profile-edit-title">프로필 수정</h2><p>프로필에 표시할 정보를 수정해 주세요.</p></div><button type="button" onClick={onClose} aria-label="프로필 수정 닫기"><span className="profile-edit-close-icon" aria-hidden="true">×</span><span className="profile-edit-close-label">편집 종료</span></button></header><form onSubmit={submit}>
    <label className="profile-edit-field required"><span>표시 이름</span><div><input value={values.displayName} onChange={event => update('displayName', event.target.value)} maxLength="40" required /></div></label>
    <label className="profile-edit-field"><span>프로필 한마디</span><div><input value={values.headline} onChange={event => update('headline', event.target.value)} maxLength="40" placeholder="좋아하는 아티스트나 요즘의 팬 관심사를 적어 주세요." /><small>프로필 배경 위에 표시되는 대표 문구입니다.</small><small className="profile-headline-count">{values.headline.length} / 40자</small></div></label>
    <label className="profile-edit-field"><span>소개글</span><div><textarea value={values.bio} onChange={event => update('bio', event.target.value)} maxLength="500" placeholder="좋아하는 아티스트, 입덕 계기, 함께 나누고 싶은 이야기를 소개해 주세요." /><small>나를 소개하면 취향이 맞는 다양한 팬 친구를 만나는 데 도움이 됩니다.</small></div></label>
    <div className="profile-edit-field profile-edit-image-field"><span>프로필 사진</span><div>{mediaPicker(avatarItems, setAvatarItems, 'avatar', '프로필 사진')}<small>최대 5장 · JPG, PNG, WebP · 장당 5MB</small></div></div>
    <div className="profile-edit-field profile-edit-image-field"><span>백그라운드 이미지</span><div>{mediaPicker(coverItems, setCoverItems, 'cover', '백그라운드 이미지')}<small>최대 5장 · 가로형 JPG, PNG, WebP · 장당 5MB</small></div></div>
    <div className="profile-edit-field"><span>SNS 계정</span><div className="profile-edit-socials">{[['facebookUrl','Facebook'],['xUrl','X / Twitter'],['instagramUrl','Instagram'],['tiktokUrl','TikTok'],['youtubeUrl','YouTube']].map(([key, label]) => <label key={key}><span>{label}</span><input type="url" value={values[key]} onChange={event => update(key, event.target.value)} placeholder="https://" /></label>)}</div></div>
    <div className="profile-edit-field"><span>나의 이미지</span><div><div className="profile-edit-gallery">{gallery.map((item, index) => <figure key={item.id}><img src={item.signedUrl} alt={`추가 이미지 ${index + 1}`} /><button type="button" onClick={() => onRemoveGallery(item)} disabled={busy} aria-label={`추가 이미지 ${index + 1} 삭제`}>×</button></figure>)}{gallery.length < 10 && <label><b>＋</b><span>이미지 추가</span><input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={onAddGallery} disabled={busy} /></label>}</div><small>최대 10장 · 이미지당 15MB</small>{status && <em>{status}</em>}</div></div>
    <label className="profile-edit-field"><span>좋아하는 음악</span><div><select value={values.favoriteTrackId} onChange={event => update('favoriteTrackId', event.target.value)}><option value="">선택하지 않음</option>{music.map(track => <option value={track[3]} key={track[3]}>{track[1]} · {track[2]}</option>)}</select></div></label>
    {saveStatus && <p className="profile-edit-status" role="status">{saveStatus}</p>}<footer><button type="button" onClick={onClose}>취소</button><button type="submit" disabled={saving}>{saving ? '저장 중…' : '변경사항 저장하기'}</button></footer>
  </form></section></div>, document.body)
}

const ProfileEditModal = ProfileEditPanel

function FanStatsGuide({ type = 'credit', onClose }) {
  useEffect(() => {
    const closeOnEscape = event => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onClose])
  const isHeat = type === 'heat'
  const guides = isHeat ? [
    ['HEAT RANGE', '최근 팬 활동의 열기를 0%부터 100%까지 보여주는 지표입니다. 꾸준히 활동할수록 범위가 채워집니다.'],
    ['활동 반영', '게시글 18, 친구 수락 12, 댓글 6, 프로필 사진 등록 4, 북마크 3, 투표 2가 적립됩니다. 삭제·취소된 활동은 제외되며 같은 대상의 재등록은 적립 시점을 갱신하지 않습니다.'],
    ['MAX', '유효한 활동으로 HEAT가 100%에 도달한 횟수입니다. 이미 100%일 때는 중복 계산하지 않으며 활동 취소 시 다시 계산합니다.'],
    ['TTL', '마지막 유효 활동 이후 HEAT가 30일에 걸쳐 감소합니다. 새 활동이 없으면 0%가 되며 TTL은 남은 일수입니다.'],
  ] : [
    ['FAN CREDIT', '다른 회원에게 게시글 추천을 받으면 3 FC, 댓글 좋아요를 받으면 1 FC가 적립됩니다. 본인 추천은 제외되며 추천 취소 시 회수됩니다.'],
    ['LEVEL', 'LV.1은 0 FC, LV.2는 100 FC, LV.3은 400 FC에서 시작합니다. 다음 레벨까지의 구간을 진행률로 표시합니다.'],
    ['RANK', '양수 FC를 가진 회원의 점수 순위입니다. 같은 FC는 공동 순위(1, 1, 3)이며 0 FC는 미집계입니다. 상위 비율은 순위 ÷ 집계 인원입니다.'],
  ]
  const title = isHeat ? 'HEAT RANGE 가이드' : 'FAN CREDIT 가이드'
  const summary = isHeat ? '현재 퍼센트와 MAX, TTL이 무엇을 의미하는지 확인해 보세요.' : 'FAN CREDIT과 레벨, 순위의 의미를 확인해 보세요.'
  return createPortal(<div className="fan-stats-guide-overlay" role="presentation" onMouseDown={event => event.target === event.currentTarget && onClose()}><section className="fan-stats-guide" role="dialog" aria-modal="true" aria-labelledby="fan-stats-guide-title"><header><div><small>FANHEAT GUIDE</small><h2 id="fan-stats-guide-title">{title}</h2><p>{summary}</p></div><button type="button" onClick={onClose} aria-label={`${title} 닫기`}>×</button></header><div className="fan-stats-guide-list">{guides.map(([name, description], index) => <article key={name}><span>{String(index + 1).padStart(2, '0')}</span><div><strong>{name}</strong><p>{description}</p></div></article>)}</div><footer><span aria-hidden="true">✦</span><p>{isHeat ? '활동이 반영되면 HEAT RANGE와 남은 기간이 갱신됩니다.' : 'FAN CREDIT이 반영되면 레벨과 순위가 갱신됩니다.'}</p><button type="button" onClick={onClose}>확인</button></footer></section></div>, document.body)
}

function SocialBrandIcon({ type }) {
  if (type === 'facebook') return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13.6 21v-8h2.8l.42-3H13.6V8.08c0-.87.24-1.46 1.62-1.46H17V3.94a24 24 0 0 0-2.31-.12c-2.29 0-3.86 1.4-3.86 3.98V10H8.2v3h2.63v8h2.77Z" /></svg>
  if (type === 'x') return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.24 2.25h3.31l-7.23 8.26 8.5 11.24h-6.65l-5.22-6.82-5.96 6.82H1.68l7.73-8.84L1.25 2.25h6.83l4.71 6.23 5.45-6.23Zm-1.16 17.52h1.84L7.08 4.13H5.12l11.96 15.64Z" /></svg>
  if (type === 'instagram') return <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="3.5" width="17" height="17" rx="5" /><circle cx="12" cy="12" r="4" /><circle className="brand-dot" cx="17.5" cy="6.7" r="1.15" /></svg>
  if (type === 'tiktok') return <svg viewBox="0 0 24 24" aria-hidden="true"><path className="tiktok-cyan" d="M15.2 3v10.2a4.9 4.9 0 1 1-4.1-4.84v2.88a2.14 2.14 0 1 0 1.3 1.96V3h2.8Z" /><path className="tiktok-red" d="M16.1 3c.32 2.08 1.5 3.34 3.4 3.76v2.83a7.2 7.2 0 0 1-3.4-1.08V3Z" /><path d="M15.65 2.55c.31 2.08 1.5 3.34 3.4 3.76v2.52a7.13 7.13 0 0 1-3.4-1.08v5.45a4.9 4.9 0 1 1-4.1-4.84v2.88a2.14 2.14 0 1 0 1.3 1.96V2.55h2.8Z" /></svg>
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21.25 7.15a2.8 2.8 0 0 0-1.97-1.98C17.54 4.7 12 4.7 12 4.7s-5.54 0-7.28.47a2.8 2.8 0 0 0-1.97 1.98A29 29 0 0 0 2.28 12c0 1.63.15 3.26.47 4.85a2.8 2.8 0 0 0 1.97 1.98c1.74.47 7.28.47 7.28.47s5.54 0 7.28-.47a2.8 2.8 0 0 0 1.97-1.98c.32-1.59.47-3.22.47-4.85s-.15-3.26-.47-4.85Z" /><path className="youtube-play" d="m10 15.2 5.2-3.2L10 8.8v6.4Z" /></svg>
}

function MyPageProfile({ user, profile, tracks = [], onBack }) {
  const initialProfileData = withProfileDisplayDefaults({
    display_name: profile?.displayName || profile?.id || user?.user_metadata?.display_name || user?.email?.split('@')[0] || 'FANHEAT',
    avatar_url: profile?.image || user?.user_metadata?.avatar_url,
    is_ai: Boolean(profile?.isAi || user?.app_metadata?.is_ai),
  })
  const [profileData, setProfileData] = useState(initialProfileData)
  const [profileEditOpen, setProfileEditOpen] = useState(false)
  const [statsGuideType, setStatsGuideType] = useState(null)
  const avatarSlides = profileData.avatar_urls?.length ? profileData.avatar_urls : [profileData.avatar_url || profile?.image || 'mypage.jpg']
  const coverSlides = profileData.cover_urls?.length ? profileData.cover_urls : [profileData.cover_url || PROFILE_DISPLAY_DEFAULTS.cover_url]
  const profileCarouselLength = Math.max(avatarSlides.length, coverSlides.length)
  const profileSlides = Array.from({ length: profileCarouselLength }, (_, index) => avatarSlides[index % avatarSlides.length])
  const profileCoverSlides = Array.from({ length: profileCarouselLength }, (_, index) => coverSlides[index % coverSlides.length])
  const music = useMemo(() => tracks.map(([title, artist, cover, row], index) => [cover || '', title, artist, row?.id ?? index + 1, row?.audio_url || '']), [tracks])
  const [slide, setSlide] = useState(0)
  const [avatarMotion, setAvatarMotion] = useState('')
  const [trackIndex, setTrackIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [gallery, setGallery] = useState([])
  const [galleryLightboxIndex, setGalleryLightboxIndex] = useState(null)
  const [fanStats, setFanStats] = useState(null)
  const [fanStatsError, setFanStatsError] = useState('')
  const [galleryBusy, setGalleryBusy] = useState(false)
  const [galleryStatus, setGalleryStatus] = useState('')
  const [profileFriendStatus, setProfileFriendStatus] = useState('none')
  const [profileFriendPending, setProfileFriendPending] = useState(false)
  const [profileFriendNotice, setProfileFriendNotice] = useState('')
  const galleryInput = useRef(null)
  const profileOwnerId = profile?.userId
  const isOtherProfile = Boolean(profileOwnerId && profileOwnerId !== user?.id)
  useEffect(() => {
    let active = true
    setProfileFriendNotice('')
    if (!isOtherProfile || !user?.id) { setProfileFriendStatus('none'); return undefined }
    setProfileFriendStatus('loading')
    loadFriendshipStatus(user.id, profileOwnerId)
      .then(status => { if (active) setProfileFriendStatus(status) })
      .catch(() => { if (active) { setProfileFriendStatus('none'); setProfileFriendNotice('친구 상태를 불러오지 못했습니다.') } })
    return () => { active = false }
  }, [isOtherProfile, profileOwnerId, user?.id])
  useEffect(() => {
    const panel = document.querySelector('.my-page-profile')
    if (!panel) return undefined
    let hideTimer
    const updateOverlayScroll = () => {
      const viewport = panel.clientHeight
      const content = panel.scrollHeight
      if (content <= viewport) return
      const thumbHeight = Math.max(52, viewport * viewport / content)
      const travel = viewport - thumbHeight - 12
      const progress = panel.scrollTop / Math.max(1, content - viewport)
      panel.style.setProperty('--profile-scroll-height', `${thumbHeight}px`)
      panel.style.setProperty('--profile-scroll-top', `${6 + travel * progress}px`)
      panel.classList.add('is-scrolling')
      window.clearTimeout(hideTimer)
      hideTimer = window.setTimeout(() => panel.classList.remove('is-scrolling'), 720)
    }
    panel.addEventListener('scroll', updateOverlayScroll, { passive: true })
    return () => { panel.removeEventListener('scroll', updateOverlayScroll); window.clearTimeout(hideTimer) }
  }, [])
  const beginAvatarMotion = direction => {
    if (profileSlides.length < 2 || avatarMotion) return
    setAvatarMotion(direction)
  }
  const profileSwipe = useSwipeCarousel({ length: profileSlides.length, index: slide, onChange: (_, direction) => beginAvatarMotion(direction), threshold: 32 })
  useEffect(() => {
    setSlide(current => current % profileSlides.length)
    setAvatarMotion('')
  }, [profileSlides.length])
  useEffect(() => {
    if (profileSlides.length < 2 || profileSwipe.dragging || avatarMotion) return undefined
    const timer = window.setInterval(() => setAvatarMotion(current => current || 'next'), 4200)
    return () => window.clearInterval(timer)
  }, [profileSlides.length, profileSwipe.dragging, avatarMotion])
  const finishAvatarMotion = () => {
    if (!avatarMotion) return
    setSlide(current => (current + (avatarMotion === 'next' ? 1 : -1) + profileSlides.length) % profileSlides.length)
    setAvatarMotion('')
  }
  useEffect(() => {
    let active = true
    const profileOwnerId = profile?.userId || user?.id
    if (!profileOwnerId) return undefined
    loadProfileCustomization(profileOwnerId).then(data => { if (active && data) { setProfileData(current => withProfileDisplayDefaults({ ...current, ...data })); const favoriteIndex = music.findIndex(track => track[3] === Number(data.favorite_track_id)); if (favoriteIndex >= 0) setTrackIndex(favoriteIndex) } }).catch(() => {})
    return () => { active = false }
  }, [profile?.userId, user?.id])
  useEffect(() => {
    let active = true
    if (profile || !user?.id) return undefined
    setGalleryBusy(true)
    loadProfileGallery(user.id).then(items => { if (active) { if (items.length) setGallery(items); setGalleryStatus('') } }).catch(() => { if (active) setGalleryStatus('') }).finally(() => { if (active) setGalleryBusy(false) })
    return () => { active = false }
  }, [profile, user?.id])
  useEffect(() => {
    let active = true
    let pending = false
    const ownerId = profile ? profile.userId : user?.id
    setFanStats(null)
    setFanStatsError('')
    if (!ownerId || !user?.id) {
      setFanStatsError('활동 통계를 보려면 로그인과 사용자 정보가 필요합니다.')
      return undefined
    }
    const refresh = async () => {
      if (pending || document.hidden) return
      pending = true
      try {
        const data = await loadFanStats(ownerId)
        if (active) { setFanStats({ ownerId, data }); setFanStatsError('') }
      } catch {
        if (active) setFanStatsError('활동 통계를 불러오지 못했습니다. 잠시 후 다시 시도합니다.')
      } finally { pending = false }
    }
    refresh()
    const timer = window.setInterval(refresh, 30000)
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      active = false
      window.clearInterval(timer)
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [profile, user?.id, galleryBusy])
  const measureGalleryImage = file => new Promise((resolve, reject) => {
    const image = new window.Image()
    const url = URL.createObjectURL(file)
    image.onload = () => { URL.revokeObjectURL(url); resolve({ file, width: image.naturalWidth, height: image.naturalHeight }) }
    image.onerror = () => { URL.revokeObjectURL(url); reject(new Error(`${file.name} 이미지를 읽을 수 없습니다.`)) }
    image.src = url
  })
  const addGalleryImages = async event => {
    const selected = [...event.target.files]
    event.target.value = ''
    const remaining = 10 - gallery.length
    if (!selected.length) return
    if (selected.length > remaining) { setGalleryStatus(`사진은 최대 10장입니다. 지금은 ${remaining}장 더 추가할 수 있습니다.`); return }
    const invalid = selected.find(file => !['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 15 * 1024 * 1024)
    if (invalid) { setGalleryStatus('JPG, PNG, WebP 이미지만 장당 15MB까지 등록할 수 있습니다.'); return }
    setGalleryBusy(true)
    setGalleryStatus('사진을 등록하고 있습니다…')
    try {
      const items = await Promise.all(selected.map(measureGalleryImage))
      const next = await uploadProfileGalleryImages(items, user.id, gallery.map(item => item.sort_order))
      setGallery(next)
      setGalleryStatus(`${selected.length}장의 사진을 등록했습니다.`)
    } catch (error) { setGalleryStatus(error.message) } finally { setGalleryBusy(false) }
  }
  const removeGalleryImage = async item => {
    if (!window.confirm('이 사진을 나의 사진에서 삭제할까요?')) return
    if (item.demo) { setGallery(current => current.filter(image => image.id !== item.id)); return }
    setGalleryBusy(true)
    setGalleryStatus('사진을 삭제하고 있습니다…')
    try {
      await deleteProfileGalleryImage(item, user.id)
      setGallery(current => current.filter(image => image.id !== item.id))
      setGalleryStatus('사진을 삭제했습니다.')
    } catch (error) { setGalleryStatus(error.message) } finally { setGalleryBusy(false) }
  }
  const toggleAudio = () => setPlaying(value => !value)
  const chooseTrack = index => { setTrackIndex(index); setPlaying(true) }
  const moveTrack = direction => { setTrackIndex(current => (current + direction + music.length) % music.length); setPlaying(true) }
  const saveProfile = async payload => { const next = await saveProfileCustomization({ userId: user.id, ...payload }); setProfileData(current => withProfileDisplayDefaults({ ...current, ...next })); const favoriteIndex = music.findIndex(track => track[3] === Number(next.favorite_track_id)); if (favoriteIndex >= 0) setTrackIndex(favoriteIndex) }
  const nickname = profile?.displayName || profile?.id || profileData.display_name
  const toggleProfileFriendRequest = async () => {
    if (!isOtherProfile || !user?.id || profileFriendPending || ['accepted', 'blocked', 'loading'].includes(profileFriendStatus)) return
    setProfileFriendPending(true)
    try {
      if (profileFriendStatus === 'pending') {
        await cancelFriendRequest(user.id, profileOwnerId)
        setProfileFriendStatus('none')
        setProfileFriendNotice(`${nickname}님에게 보낸 친구 요청을 취소했습니다.`)
      } else {
        await sendFriendRequest(user.id, profileOwnerId)
        setProfileFriendStatus('pending')
        setProfileFriendNotice(`${nickname}님에게 친구 요청을 보냈습니다.`)
      }
    } catch {
      setProfileFriendNotice('친구 요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.')
    } finally { setProfileFriendPending(false) }
  }
  const isAiProfile = Boolean(profileData.is_ai || profile?.isAi)
  const aiProfileGallery = profile && isAiProfile
    ? (profileData.avatar_urls || []).slice(1).map((url, index) => ({
      id: `ai-profile-memory-${index}`,
      signedUrl: assetSrc(url),
      readOnly: true,
    }))
    : []
  const visibleGallery = profile ? aiProfileGallery : gallery
  const fanStatSource = fanStats?.ownerId === (profile ? profile.userId : user?.id) ? fanStats.data : null
  const fanCred = Math.max(0, Number(fanStatSource?.fan_credit) || 0)
  const heatMaxCount = Math.max(0, Number(fanStatSource?.heat_max_count) || 0)
  const heat = Math.max(0, Math.min(100, Number(fanStatSource?.heat_range) || 0))
  const heatDaysRemaining = Math.max(0, Number(fanStatSource?.heat_days_remaining) || 0)
  const fanLevelStats = calculateFanLevel(fanCred)
  const fanLevel = fanLevelStats.level
  const credProgress = fanLevelStats.progress
  const fanRank = calculateFanRank(fanStatSource?.fan_rank, fanStatSource?.fan_rank_total)
  const fanRankTotal = fanRank.total
  const fanRankPosition = fanRank.position
  const fanTopPercent = fanRank.topPercent
  const socialLinks = [
    ['facebook', profileData.facebook_url, 'Facebook'],
    ['x', profileData.x_url, 'X / Twitter'],
    ['instagram', profileData.instagram_url, 'Instagram'],
    ['tiktok', profileData.tiktok_url, 'TikTok'],
    ['youtube', profileData.youtube_url, 'YouTube'],
  ].filter(([, url]) => Boolean(url))
  const headlineContent = profileData._profile_headline_is_set ? profileData.profile_headline : '미작성 (좋아하는 아티스트나 팬 관심사를 한 줄로 소개해 주세요.)'
  const bioContent = profileData._bio_is_set ? profileData.bio : '미작성 (나를 소개하고 취향이 맞는 다양한 팬 친구를 만나보세요.)'
  return <section className="my-page-profile"><div className="my-cover" style={{ backgroundImage: `linear-gradient(90deg,rgba(11,9,16,.83),rgba(10,8,15,.28)),url(${assetSrc(profileCoverSlides[slide])})` }}><button className="my-cover-back" type="button" onClick={onBack} aria-label="이전 화면으로 돌아가기"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5-7 7 7 7" /></svg></button>{!profile && <button className="my-profile-edit-button" type="button" onClick={() => setProfileEditOpen(true)}>프로필 수정</button>}{isOtherProfile && <button className={`my-profile-friend-button ${profileFriendStatus}`} type="button" onClick={toggleProfileFriendRequest} disabled={profileFriendPending || ['loading', 'accepted', 'blocked'].includes(profileFriendStatus)}>{profileFriendPending ? '처리 중…' : profileFriendStatus === 'pending' ? '요청됨' : profileFriendStatus === 'accepted' ? '✓ 친구' : profileFriendStatus === 'blocked' ? '추가 불가' : profileFriendStatus === 'loading' ? '확인 중…' : '＋ 친구 추가'}</button>}{profileFriendNotice && <p className="my-profile-friend-notice" role="status">{profileFriendNotice}</p>}<div className="my-cover-copy"><h1>{nickname}</h1>{!profile && !profileData._profile_headline_is_set ? <button className="my-profile-empty-headline" type="button" onClick={() => setProfileEditOpen(true)}>{headlineContent}</button> : <p className={!profileData._profile_headline_is_set ? 'is-empty' : ''}>{headlineContent}</p>}<span>K-POP FAN</span>{!profile && socialLinks.length > 0 && <div className="my-profile-socials">{socialLinks.map(([type, url, label]) => <a className={`social-${type}`} href={url} target="_blank" rel="noreferrer" aria-label={`${label} 프로필 열기`} title={label} key={type}><SocialBrandIcon type={type} /></a>)}</div>}</div><button className="my-cover-play" onClick={toggleAudio} aria-label={playing ? '대표 음원 일시정지' : '대표 음원 재생'}>{playing ? 'Ⅱ' : '▶'}</button></div><div className={`my-avatar-carousel ${profileSwipe.dragging ? 'is-dragging' : ''}`}><button type="button" onClick={() => beginAvatarMotion('prev')} disabled={Boolean(avatarMotion)} aria-label="이전 프로필">‹</button><div className="my-avatar-viewport" {...profileSwipe.bind}><div className={`my-avatar-track ${avatarMotion ? `move-${avatarMotion}` : ''}`} style={!avatarMotion && profileSwipe.dragOffset ? { transform: `translate3d(calc(-33.333333% + ${profileSwipe.dragOffset}px),0,0)` } : undefined} onTransitionEnd={finishAvatarMotion}>{[-1, 0, 1].map(offset => { const index = (slide + offset + profileSlides.length) % profileSlides.length; return <img src={assetSrc(profileSlides[index])} onError={event => { event.currentTarget.onerror = null; event.currentTarget.src = PROFILE_DISPLAY_DEFAULTS.avatar_url }} alt={offset === 0 ? `${nickname} 프로필` : ''} aria-hidden={offset !== 0} draggable="false" key={`${index}-${offset}`} /> })}</div></div>{isAiProfile && <span className="ai-profile-badge" aria-label="FANHEAT AI 프로필"><i aria-hidden="true">✦</i><b>AI</b><i aria-hidden="true">✦</i></span>}<button type="button" onClick={() => beginAvatarMotion('next')} disabled={Boolean(avatarMotion)} aria-label="다음 프로필">›</button><div>{profileSlides.map((_, index) => <i key={index} className={slide === index ? 'active' : ''} />)}</div></div><div className="my-profile-body">{fanStatsError && <p role="status">{fanStatsError}</p>}{!fanStatSource && !fanStatsError && <p role="status">활동 통계를 불러오는 중입니다.</p>}{fanStatSource && <section className="my-resources"><article className={heat === 100 ? 'heat-range-card is-max' : 'heat-range-card'}><header><strong>HEAT RANGE</strong><div className="heat-range-level"><span>{heat}%</span><button className="fan-stats-guide-button" type="button" onClick={() => setStatsGuideType('heat')} aria-label="HEAT RANGE 안내 보기">?</button></div></header><div><i style={{ width: `${heat}%` }} /></div><footer>{heat === 100 ? <b>MAX · 100% 달성</b> : <small>활동을 이어가면 100% 달성</small>}</footer></article><article className="fan-cred-card"><header><strong>FAN CREDIT</strong><div className="fan-credit-level"><span>LV.{fanLevel}</span><button className="fan-stats-guide-button" type="button" onClick={() => setStatsGuideType('credit')} aria-label="FAN CREDIT 안내 보기">?</button></div></header><div><i style={{ width: `${Math.max(0, Math.min(100, credProgress))}%` }} /></div><footer><b>{fanCred.toLocaleString()} FC</b><small>다음 레벨까지 {fanLevelStats.creditToNextLevel.toLocaleString()} FC</small></footer></article><dl><div><dt>MAX</dt><dd><b>{heatMaxCount.toLocaleString()}회</b><small>100% 달성</small></dd></div><div><dt>TTL</dt><dd><b>{heatDaysRemaining}일</b><small>HEAT 소멸까지</small></dd></div><div className="fan-cred-summary"><dt>RANK</dt><dd><b>{fanRankPosition ? `${fanRankPosition.toLocaleString()}위 / ${fanRankTotal.toLocaleString()}명` : '미집계'}</b><small>{fanRankPosition ? `상위 ${fanTopPercent}%` : 'FC 적립 후 순위 반영'}</small></dd></div></dl></section>}{!profile && !profileData._bio_is_set ? <button className="my-intro my-profile-empty-intro" type="button" onClick={() => setProfileEditOpen(true)}>{bioContent}</button> : <p className={`my-intro ${!profileData._bio_is_set ? 'is-empty' : ''}`}>{bioContent}</p>}{(!profile || aiProfileGallery.length > 0) && <section className="my-gallery"><header><div><h2>{profile ? '프로필 사진' : '나의 사진'}</h2><p>{profile ? `${nickname}의 소중한 순간을 모았습니다.` : '나만의 순간을 썸네일로 모아보세요.'}</p></div><span>{profile ? visibleGallery.length : `${visibleGallery.length} / 10`}</span></header><div className="my-gallery-grid">{visibleGallery.map((item, index) => <figure key={item.id}><img src={item.signedUrl} alt={`${profile ? `${nickname} 프로필 사진` : '나의 사진'} ${index + 1} 크게 보기`} role="button" tabIndex="0" onClick={() => setGalleryLightboxIndex(index)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setGalleryLightboxIndex(index) } }} />{!profile && <button type="button" onClick={() => removeGalleryImage(item)} disabled={galleryBusy} aria-label={`나의 사진 ${index + 1} 삭제`}>×</button>}</figure>)}{!profile && gallery.length < 10 && <button className="my-gallery-add" type="button" onClick={() => galleryInput.current?.click()} disabled={galleryBusy}><b>＋</b><span>{galleryBusy ? '처리 중' : '사진 추가'}</span></button>}</div>{!profile && <><input ref={galleryInput} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden onChange={addGalleryImages} />{galleryStatus && <p className="my-gallery-status" role="status">{galleryStatus}</p>}<small>JPG · PNG · WebP / 장당 최대 15MB</small></>}</section>}{/* My Music is intentionally disabled for now. Set USER_MUSIC_PLAYBACK_ENABLED to true to restore it. */}{USER_MUSIC_PLAYBACK_ENABLED && <section className="my-music"><header><h2>My뮤직</h2><span>Total : {music.length}</span></header>{music.map((item, index) => <button key={item[3]} className={trackIndex === index ? 'active' : ''} onClick={() => chooseTrack(index)}><b>{index + 1}</b><img src={assetSrc(item[0])} alt="" /><span><strong>{item[1]}</strong><small>{item[2]}</small></span><em>{trackIndex === index && playing ? 'Ⅱ' : '▶'}</em></button>)}</section>}</div>{galleryLightboxIndex !== null && visibleGallery.length > 0 && <ImageLightbox images={visibleGallery.map((item, index) => ({ type: 'image', src: item.signedUrl, imageIndex: index }))} initialIndex={galleryLightboxIndex} title={nickname + ' 프로필 이미지'} onClose={() => setGalleryLightboxIndex(null)} />}<MyPageAudioPlayer track={music[trackIndex]} playing={playing} onPlayingChange={setPlaying} onPrevious={() => moveTrack(-1)} onNext={() => moveTrack(1)} />{statsGuideType && <FanStatsGuide type={statsGuideType} onClose={() => setStatsGuideType(null)} />}{!profile && profileEditOpen && <ProfileEditModal initial={profileData} music={music} gallery={gallery} busy={galleryBusy} status={galleryStatus} onAddGallery={addGalleryImages} onRemoveGallery={removeGalleryImage} onClose={() => setProfileEditOpen(false)} onSave={saveProfile} />}</section>
}

function MessageCenter({ user, onUnreadChange }) {
  const [messages, setMessages] = useState([])
  const [contacts, setContacts] = useState([])
  const [blocks, setBlocks] = useState([])
  const [folder, setFolder] = useState('inbox')
  const [selectedId, setSelectedId] = useState(null)
  const [composeOpen, setComposeOpen] = useState(false)
  const [recipientId, setRecipientId] = useState('')
  const [replyToId, setReplyToId] = useState(null)
  const [body, setBody] = useState('')
  const [query, setQuery] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const refresh = async () => {
    if (!user?.id) return
    const [messageRows, contactRows, blockRows] = await Promise.all([
      loadPrivateMessages(user.id),
      loadMessageContacts(user.id),
      loadMessageBlocks(user.id),
    ])
    setMessages(messageRows); setContacts(contactRows); setBlocks(blockRows)
    onUnreadChange?.(messageRows.filter(message => message.recipient_id === user.id && !message.read_at).length)
  }
  useEffect(() => {
    let active = true
    if (!user?.id) return undefined
    Promise.all([loadPrivateMessages(user.id), loadMessageContacts(user.id), loadMessageBlocks(user.id)])
      .then(([messageRows, contactRows, blockRows]) => {
        if (!active) return
        setMessages(messageRows); setContacts(contactRows); setBlocks(blockRows); setNotice('')
        onUnreadChange?.(messageRows.filter(message => message.recipient_id === user.id && !message.read_at).length)
      })
      .catch(error => { if (active) setNotice(`쪽지를 불러오지 못했습니다: ${error.message}`) })
    return () => { active = false }
  }, [user?.id])
  const inbox = messages.filter(message => message.recipient_id === user?.id)
  const sent = messages.filter(message => message.sender_id === user?.id)
  const unread = inbox.filter(message => !message.read_at).length
  const rows = folder === 'sent' ? sent : inbox
  const normalizedQuery = query.trim().toLocaleLowerCase('ko-KR')
  const visibleRows = rows.filter(message => {
    const person = folder === 'sent' ? message.recipient : message.sender
    return !normalizedQuery || `${person?.display_name || ''} ${message.body}`.toLocaleLowerCase('ko-KR').includes(normalizedQuery)
  })
  const selectMessage = async message => {
    setSelectedId(message.id)
    if (message.recipient_id !== user.id || message.read_at) return
    try {
      await markPrivateMessageRead(message.id, user.id)
      const readAt = new Date().toISOString()
      setMessages(current => current.map(item => item.id === message.id ? { ...item, read_at: readAt } : item))
      onUnreadChange?.(Math.max(0, unread - 1))
    } catch (error) { setNotice(`읽음 처리에 실패했습니다: ${error.message}`) }
  }
  const openCompose = (recipient = '', reply = null) => {
    setRecipientId(recipient); setReplyToId(reply); setBody(''); setNotice(''); setComposeOpen(true)
  }
  const submit = async event => {
    event.preventDefault(); setBusy(true); setNotice('')
    try {
      const next = await sendPrivateMessage({ senderId: user.id, recipientId, body, replyToId })
      setMessages(current => [next, ...current]); setComposeOpen(false); setFolder('sent'); setSelectedId(next.id); setBody(''); setReplyToId(null)
      setNotice('쪽지를 보냈습니다.')
    } catch (error) {
      const blocked = error.code === '42501' || /row-level security|policy/i.test(error.message || '')
      setNotice(blocked ? '차단 관계인 사용자에게는 쪽지를 보낼 수 없습니다.' : `쪽지를 보내지 못했습니다: ${error.message}`)
    } finally { setBusy(false) }
  }
  const toggleBlock = async (profile, blocked) => {
    if (!profile?.id) return
    if (blocked && !window.confirm(`${profile.display_name || '이 사용자'}님의 쪽지를 완전히 차단할까요? 서로 새 쪽지를 보낼 수 없게 됩니다.`)) return
    setBusy(true); setNotice('')
    try {
      await setMessageBlock(user.id, profile.id, blocked)
      await refresh()
      if (blocked) { setSelectedId(null); setNotice(`${profile.display_name || '사용자'}님의 쪽지를 차단했습니다.`) }
      else setNotice(`${profile.display_name || '사용자'}님의 차단을 해제했습니다.`)
    } catch (error) { setNotice(`차단 설정을 바꾸지 못했습니다: ${error.message}`) }
    finally { setBusy(false) }
  }
  const formatMessageTime = value => new Date(value).toLocaleString('ko-KR', { dateStyle: 'medium', timeStyle: 'short' })
  return <section className="message-center">
    <nav className="message-folders" aria-label="쪽지함 메뉴">
      <button type="button" className={folder === 'inbox' ? 'active' : ''} onClick={() => { setFolder('inbox'); setSelectedId(null) }}>받은 쪽지 <b>{inbox.length}</b>{unread > 0 && <em>{unread} NEW</em>}</button>
      <button type="button" className={folder === 'sent' ? 'active' : ''} onClick={() => { setFolder('sent'); setSelectedId(null) }}>보낸 쪽지 <b>{sent.length}</b></button>
      <button type="button" className={folder === 'blocked' ? 'active' : ''} onClick={() => { setFolder('blocked'); setSelectedId(null) }}>차단 사용자 <b>{blocks.length}</b></button>
      <button type="button" className="message-new-button" onClick={() => openCompose()}>＋ 새 쪽지</button>
    </nav>
    {notice && <p className="message-notice" role="status">{notice}</p>}
    {folder === 'blocked' ? <div className="message-block-list">{blocks.map(block => <article key={block.blocked_user_id}><img src={assetSrc(block.blocked?.avatar_url || 'mypage.jpg')} alt="" /><div><strong>{block.blocked?.display_name || 'FAN'}</strong><span>{formatMessageTime(block.created_at)}부터 차단됨</span></div><button type="button" disabled={busy} onClick={() => toggleBlock(block.blocked, false)}>차단 해제</button></article>)}{!blocks.length && <p>차단한 사용자가 없습니다.</p>}</div> : <div className="message-list-shell">
      <label className="message-search"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/></svg><input value={query} onChange={event => setQuery(event.target.value)} placeholder="이름 또는 내용 검색" aria-label="쪽지 검색" />{query && <button type="button" onClick={() => setQuery('')} aria-label="검색어 지우기">×</button>}</label>
      <div className="message-board-head" aria-hidden="true"><span>번호</span><span></span><span>{folder === 'sent' ? '받는 사람' : '보낸 사람'}</span><span>내용</span><span>날짜</span><span>상태</span><span></span></div>
      <div className="message-list" role="list">{visibleRows.map((message, index) => { const profile = folder === 'sent' ? message.recipient : message.sender; const isUnread = folder === 'inbox' && !message.read_at; const isSelected = selectedId === message.id; const isBlocked = Boolean(profile && blocks.some(block => block.blocked_user_id === profile.id)); return <article className={`message-row ${isSelected ? 'active' : ''} ${isUnread ? 'unread' : ''}`} role="listitem" key={message.id}><button type="button" className="message-row-summary" onClick={() => isSelected ? setSelectedId(null) : selectMessage(message)} aria-expanded={isSelected}><span className="message-row-number">{String(index + 1).padStart(2, '0')}</span><img src={assetSrc(profile?.avatar_url || 'mypage.jpg')} alt="" /><span className="message-row-person"><strong>{profile?.display_name || 'FAN'}{isUnread && <i>NEW</i>}</strong><small>{folder === 'sent' ? '받는 사람' : '보낸 사람'}</small></span><q>{message.body}</q><time>{formatMessageTime(message.created_at)}</time><em className={message.read_at ? 'read' : ''}>{folder === 'sent' ? (message.read_at ? '읽음' : '안 읽음') : (isUnread ? '새 쪽지' : '읽음')}</em><span className="message-row-chevron" aria-hidden="true">⌄</span></button>{isSelected && <div className="message-row-detail"><p>{message.body}</p><footer><span>{message.recipient_id === user.id ? '확인한 쪽지' : message.read_at ? '상대방이 읽었습니다.' : '아직 읽지 않았습니다.'}</span><div><button type="button" className={isBlocked ? 'blocked' : ''} disabled={busy} onClick={() => toggleBlock(profile, !isBlocked)}>{isBlocked ? '차단 해제' : '사용자 차단'}</button>{!isBlocked && <button type="button" className="reply" onClick={() => openCompose(profile?.id, message.id)}>↩ 답장하기</button>}</div></footer></div>}</article>})}{!visibleRows.length && <p className="message-empty">{query ? '검색한 쪽지가 없습니다.' : folder === 'inbox' ? '받은 쪽지가 없습니다.' : '보낸 쪽지가 없습니다.'}</p>}</div>
    </div>}
    {composeOpen && <div className="message-compose-overlay" role="presentation" onMouseDown={event => event.target === event.currentTarget && setComposeOpen(false)}><form className="message-compose" onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="message-compose-title"><header><div><small>{replyToId ? 'REPLY MESSAGE' : 'NEW MESSAGE'}</small><h2 id="message-compose-title">{replyToId ? '쪽지 답장' : '새 쪽지'}</h2></div><button type="button" onClick={() => setComposeOpen(false)} aria-label="쪽지 작성 닫기">×</button></header><label><span>받는 사람</span><select value={recipientId} onChange={event => setRecipientId(event.target.value)} required><option value="">사용자를 선택해 주세요</option>{contacts.filter(contact => !blocks.some(block => block.blocked_user_id === contact.id)).map(contact => <option value={contact.id} key={contact.id}>{contact.display_name || 'FAN'}</option>)}</select></label><label><span>쪽지 내용</span><textarea value={body} onChange={event => setBody(event.target.value)} maxLength="2000" placeholder="팬에게 전할 이야기를 입력해 주세요." required /><small>{body.length.toLocaleString()} / 2,000</small></label><footer><button type="button" onClick={() => setComposeOpen(false)}>취소</button><button type="submit" disabled={busy || !recipientId || !body.trim()}>{busy ? '보내는 중…' : '쪽지 보내기'}</button></footer></form></div>}
  </section>
}

function MyPostListThumbnail({ title, image, data }) {
  const storedImage = image || (Array.isArray(data?.images) ? data.images.find(Boolean) : '')
  const source = storedImage ? assetSrc(storedImage) : youtubeThumbnailUrl(data?.reference_url || data?.source_url)
  if (!source) return <span className="my-post-thumbnail my-post-thumbnail-empty" aria-label="등록된 이미지 없음">이미지 없음</span>
  return <img className="my-post-thumbnail" src={source} alt={`${title || '포스트'} 썸네일`} />
}

function MyPageContent({ user, posts: items, followers, unreadMessageCount = 0, onSelect, onOpenFriend, onUnreadChange, initialTab = 'posts', publicProfile = null }) {
  const isPublicProfile = Boolean(publicProfile)
  const [friends, setFriends] = useState([])
  const [friendQuery, setFriendQuery] = useState('')
  const [friendInvites, setFriendInvites] = useState([])
  const [friendInvitesOpen, setFriendInvitesOpen] = useState(false)
  const [friendNotice, setFriendNotice] = useState('')
  const [tab, setTab] = useState(initialTab)
  const [sort, setSort] = useState('latest')
  const [listQuery, setListQuery] = useState('')
  const [commentPage, setCommentPage] = useState(1)
  const [myComments, setMyComments] = useState([])
  const [commentError, setCommentError] = useState('')
  const [bookmarks, setBookmarks] = useState([])
  const [bookmarkError, setBookmarkError] = useState('')
  const [messageCount, setMessageCount] = useState(unreadMessageCount)
  useEffect(() => setMessageCount(unreadMessageCount), [unreadMessageCount])
  useEffect(() => setTab(initialTab), [initialTab])
  useEffect(() => {
    let active = true
    if (!user?.id || isPublicProfile) return undefined
    loadUserComments(user.id).then(rows => { if (active) { setMyComments(rows); setCommentError('') } }).catch(error => { if (active) setCommentError(error.message) })
    return () => { active = false }
  }, [user?.id, isPublicProfile])
  useEffect(() => {
    let active = true
    if (!user?.id || isPublicProfile) { setBookmarks([]); return undefined }
    loadUserBookmarks(user.id).then(rows => { if (active) { setBookmarks(rows); setBookmarkError('') } }).catch(error => { if (active) setBookmarkError(error.message) })
    return () => { active = false }
  }, [user?.id, isPublicProfile])
  useEffect(() => {
    let active = true
    if (!user?.id || isPublicProfile) return undefined
    loadBestFriends(user.id).then(rows => {
      if (!active) return
      setFriends(rows.map(row => [
        `@${String(row.display_name || 'fan').replace(/^@/, '')}`,
        0,
        row.avatar_url || 'mypage.jpg',
        Number(row.interaction_score || 0),
        {
          friendId: row.friend_id,
          starLevel: Number(row.star_level || 0),
          sharedPostCount: Number(row.shared_post_count || 0),
          commentsOnMyPosts: Number(row.comments_on_my_posts || 0),
          repliesToMyComments: Number(row.replies_to_my_comments || 0),
        },
      ]))
    }).catch(() => { if (active) setFriends([]) })
    return () => { active = false }
  }, [user?.id, isPublicProfile])
  useEffect(() => {
    let active = true
    if (!publicProfile?.userId) return undefined
    loadPublicProfileFriends(publicProfile.userId).then(rows => {
      if (!active) return
      setFriends(rows.map(row => [`@${String(row.display_name || 'fan').replace(/^@/, '')}`, 0, row.avatar_url || 'mypage.jpg', 0, { friendId: row.id }]))
    }).catch(() => { if (active) setFriends([]) })
    return () => { active = false }
  }, [publicProfile?.userId])
  useEffect(() => {
    if (!friendInvitesOpen) return undefined
    if (!friendInvites.length) { setFriendInvitesOpen(false); return undefined }
    const closeOnEscape = event => event.key === 'Escape' && setFriendInvitesOpen(false)
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [friendInvitesOpen, friendInvites.length])
  const profileOwnerId = publicProfile?.userId || user?.id
  const owned = items.filter(([, , data]) => data?.author_id === profileOwnerId)
  const bookmarkedPosts = bookmarks.map(bookmark => items.find(([, , data]) => data?.id === bookmark.post_id)).filter(Boolean)
  const normalizedListQuery = listQuery.trim().toLocaleLowerCase('ko-KR')
  const sourcePosts = tab === 'bookmarks' ? bookmarkedPosts : owned
  const filteredPosts = sourcePosts.filter(([title, , data]) => !normalizedListQuery || `${title || ''} ${data?.summary || ''}`.toLocaleLowerCase('ko-KR').includes(normalizedListQuery))
  const visiblePosts = filteredPosts.slice(0, 8)
  const sortedPosts = sort === 'popular' ? [...visiblePosts].sort((a, b) => (b[2]?.vote_count || 0) - (a[2]?.vote_count || 0)) : visiblePosts
  const tabs = isPublicProfile ? [['posts','POST',owned.length],['followers','FRIENDS',friends.length]] : [['posts','POST',owned.length],['bookmarks','BOOKMARK',bookmarks.length],['followers','FRIENDS',friends.length],['comments','COMMENT',myComments.length],['messages','MESSAGE',messageCount]]
  const commentItems = myComments.map(comment => {
    const item = items.find(([, , data]) => data?.id === comment.post_id)
    return { comment, item }
  })
  const sortedCommentItems = commentItems.filter(({ comment }) => !normalizedListQuery || (comment.body || '').toLocaleLowerCase('ko-KR').includes(normalizedListQuery)).sort((a, b) => new Date(b.comment.created_at) - new Date(a.comment.created_at))
  const commentPageSize = 10
  const commentPageCount = Math.max(1, Math.ceil(sortedCommentItems.length / commentPageSize))
  const pagedCommentItems = sortedCommentItems.slice((commentPage - 1) * commentPageSize, commentPage * commentPageSize)
  useEffect(() => setCommentPage(1), [listQuery, tab])
  useEffect(() => setCommentPage(current => Math.min(current, commentPageCount)), [commentPageCount])
  if (isPublicProfile && tab === 'followers') {
    const visibleFriends = friends.filter(([id]) => id.toLowerCase().includes(friendQuery.trim().toLowerCase()))
    return <section className="my-page-content public-profile-content"><div className="my-page-tabs">{tabs.map(([key, label, count]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}<b>{count}</b></button>)}</div><section className="friends-directory"><header className="friends-tools"><label><span aria-hidden="true">⌕</span><input value={friendQuery} onChange={event => setFriendQuery(event.target.value)} placeholder="친구 계정 ID 검색" />{friendQuery && <button type="button" onClick={() => setFriendQuery('')}>×</button>}</label><div><small>TOTAL FRIENDS</small><strong>{friends.length}</strong></div></header><div className="my-followers">{visibleFriends.map(([id, , image, , metrics = {}]) => <article key={metrics.friendId || id}><img src={assetSrc(image)} alt={`${id} 프로필`} /><div className="friend-account"><span>{id}</span><button type="button" onClick={() => onOpenFriend({ userId: metrics.friendId, id, image, artist: 'FANHEAT' })} aria-label={`${id} 프로필로 이동`} title="친구 프로필"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 10 8-6 8 6v9a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1v-9Z" /></svg></button></div></article>)}</div>{!visibleFriends.length && <p className="friends-empty">표시할 친구가 없습니다.</p>}</section></section>
  }
  if (tab === 'messages') {
    const updateUnread = count => { setMessageCount(count); onUnreadChange?.(count) }
    return <section className="my-page-content"><div className="my-page-tabs">{tabs.map(([key, label, count]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}<b>{count}</b></button>)}</div><MessageCenter user={user} onUnreadChange={updateUnread} /></section>
  }
  if (tab === 'followers') {
    const rankedFriends = [...friends].sort((a, b) => b[3] - a[3])
    const visibleFriends = rankedFriends.filter(([id]) => id.toLowerCase().includes(friendQuery.trim().toLowerCase()))
    const inviteFriend = async () => {
      const invite = { title: 'FANHEAT 친구 초대', text: 'FANHEAT에서 K-POP 이야기를 함께 나눠요!', url: window.location.href }
      try { if (navigator.share) await navigator.share(invite); else { await navigator.clipboard.writeText(`${invite.text} ${invite.url}`); setFriendNotice('친구 초대 링크를 복사했습니다.') } } catch (error) { if (error.name !== 'AbortError') setFriendNotice('초대 링크를 만들지 못했습니다.') }
    }
    const acceptInvite = index => { const accepted = friendInvites[index]; setFriends(current => [...current, accepted]); setFriendInvites(current => current.filter((_, itemIndex) => itemIndex !== index)); if (friendInvites.length === 1) setFriendInvitesOpen(false); setFriendNotice(`${accepted[0]}님과 친구가 되었습니다.`) }
    return <section className="my-page-content"><div className="my-page-tabs">{tabs.map(([key, label, count]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}<b>{key === 'followers' ? friends.length : count}</b></button>)}</div><section className="friends-directory"><header className="friends-tools"><label><span aria-hidden="true">⌕</span><input value={friendQuery} onChange={event => setFriendQuery(event.target.value)} placeholder="친구 계정 ID 검색" />{friendQuery && <button type="button" onClick={() => setFriendQuery('')}>×</button>}</label><button className="friends-invite-button" type="button" onClick={inviteFriend}>＋ INVITE</button>{friendInvites.length > 0 && <button className="friend-invite-tag" type="button" onClick={() => setFriendInvitesOpen(true)}><span>받은 초대</span><b>{friendInvites.length}</b></button>}<div><small>TOTAL FRIENDS</small><strong>{friends.length}</strong></div></header>{friendNotice && <p className="friend-notice">{friendNotice}</p>}<div className="my-followers">{visibleFriends.map(friend => { const [id, , image, interaction, metrics = {}] = friend; const rankIndex = rankedFriends.indexOf(friend); const starLevel = Number(metrics.starLevel ?? (rankIndex < 5 ? 5 - rankIndex : 0)); const scoreTitle = `같은 포스트 ${metrics.sharedPostCount || 0}회 · 내 글 댓글 ${metrics.commentsOnMyPosts || 0}회 · 내 댓글 답글 ${metrics.repliesToMyComments || 0}회 · 총 ${interaction}점`; return <article className={starLevel > 0 ? `best-friend best-friend-level-${starLevel}` : ''} title={scoreTitle} key={metrics.friendId || id}>{starLevel > 0 && <em className={`best-friend-tier tier-${starLevel}`} aria-label={`베스트 프렌드 ${starLevel}단계`}><span aria-hidden="true">{'★'.repeat(starLevel)}</span><small>BF</small></em>}<img src={assetSrc(image)} alt={`${id} 프로필`} /><div className="friend-account"><span>{id}</span><button type="button" onClick={() => onOpenFriend({ id: metrics.friendId || id, image, activity: interaction, artist: 'FANHEAT' })} aria-label={`${id} 소개 페이지로 이동`} title="친구 홈"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 10 8-6 8 6v9a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1v-9Z" /></svg></button></div><small className="best-friend-score">교감 {Number(interaction || 0).toLocaleString()}점</small></article> })}</div>{!visibleFriends.length && <p className="friends-empty">검색한 친구가 없습니다.</p>}</section>{friendInvitesOpen && <div className="friend-invite-overlay" role="presentation" onMouseDown={event => event.target === event.currentTarget && setFriendInvitesOpen(false)}><section className="friend-invite-modal" role="dialog" aria-modal="true" aria-labelledby="friend-invite-title"><header><div><small>FRIEND REQUESTS</small><h2 id="friend-invite-title">받은 친구 초대</h2><p>나와 친구가 되고 싶은 팬들을 확인해 보세요.</p></div><button type="button" onClick={() => setFriendInvitesOpen(false)} aria-label="받은 친구 초대 닫기">×</button></header><div className="friend-invite-list">{friendInvites.map(([id, , image], index) => <article key={id}><img src={assetSrc(image)} alt={`${id} 프로필`} /><div><strong>{id}</strong><span>FANHEAT에서 친구 초대를 보냈습니다.</span></div><button type="button" onClick={() => acceptInvite(index)}>수락</button><button type="button" className="decline" onClick={() => setFriendInvites(current => current.filter((_, itemIndex) => itemIndex !== index))}>거절</button></article>)}</div></section></div>}</section>
  }
  return <section className="my-page-content">
    <div className="my-page-tabs">
      {tabs.map(([key, label, count]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}<b>{count}</b></button>)}
    </div>
    <div className="my-list-toolbar">
      <div className="my-list-tools">
        <div className="my-list-search"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/></svg><input value={listQuery} onChange={event => setListQuery(event.target.value)} placeholder={tab === 'comments' ? '댓글 내용 검색' : '포스트 검색'} aria-label={tab === 'comments' ? '댓글 내용 검색' : '포스트 검색'} />{listQuery && <button type="button" onClick={() => setListQuery('')} aria-label="검색어 지우기">×</button>}</div>
        <label className="my-list-sort"><span>정렬</span><select value={tab === 'comments' ? 'latest' : sort} onChange={event => setSort(event.target.value)}><option value="latest">최신순</option>{tab !== 'comments' && <option value="popular">보상점수</option>}</select></label>
      </div>
    </div>
    {tab === 'comments' ? <div className="my-comment-history">
      {commentError && <p className="my-comment-empty">댓글을 불러오지 못했습니다: {commentError}</p>}
      {!commentError && !commentItems.length && <p className="my-comment-empty">아직 작성한 댓글이 없습니다.</p>}
      {!commentError && commentItems.length > 0 && !sortedCommentItems.length && <p className="my-comment-empty">검색 결과가 없습니다.</p>}
      {pagedCommentItems.map(({ comment, item }, index) => {
        const [title = '삭제되었거나 비공개된 포스트', image = '', data = {}] = item || []
        return <button key={comment.id} onClick={() => item && onSelect({ title, image, index: items.indexOf(item), data, editCommentId: comment.id })} disabled={!item}>
          <span className="my-comment-rank">{String((commentPage - 1) * commentPageSize + index + 1).padStart(2, '0')}</span>
          {image && <img src={assetSrc(image)} alt="" />}
          <span className="my-comment-copy"><q>{comment.body}</q><span className="my-comment-reactions"><span aria-label={`좋아요 ${Number(comment.like_count || 0).toLocaleString()}건`}><span aria-hidden="true">👍</span> 좋아요 {Number(comment.like_count || 0).toLocaleString()}건</span><i aria-hidden="true">·</i><span aria-label={`싫어요 ${Number(comment.dislike_count || 0).toLocaleString()}건`}><span aria-hidden="true">👎</span> 싫어요 {Number(comment.dislike_count || 0).toLocaleString()}건</span></span></span>
          <time>{new Date(comment.created_at).toLocaleString('ko-KR', { dateStyle: 'medium', timeStyle: 'short' })}</time>
          <em><span>포스트 보기</span><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M6 14 14 6m-6 0h6v6" /></svg></em>
        </button>
      })}
      <footer className="my-board-footer"><span>Total <b>{sortedCommentItems.length}</b></span><nav aria-label="댓글 목록 페이지"><button type="button" onClick={() => setCommentPage(page => Math.max(1, page - 1))} disabled={commentPage === 1} aria-label="이전 페이지">‹</button>{Array.from({ length: commentPageCount }, (_, index) => index + 1).map(page => <button type="button" className={commentPage === page ? 'active' : ''} onClick={() => setCommentPage(page)} aria-current={commentPage === page ? 'page' : undefined} key={page}>{page}</button>)}<button type="button" onClick={() => setCommentPage(page => Math.min(commentPageCount, page + 1))} disabled={commentPage === commentPageCount} aria-label="다음 페이지">›</button></nav></footer>
    </div> : <div className="my-post-list">
      {tab === 'bookmarks' && bookmarkError && <p className="my-bookmark-empty">북마크를 불러오지 못했습니다: {bookmarkError}</p>}
      {normalizedListQuery && !sortedPosts.length && <p className="my-bookmark-empty">검색 결과가 없습니다.</p>}
      {tab === 'bookmarks' && !bookmarkError && !normalizedListQuery && !sortedPosts.length && <p className="my-bookmark-empty">아직 저장한 북마크가 없습니다.</p>}
      {tab === 'posts' && !normalizedListQuery && !sortedPosts.length && <p className="my-bookmark-empty">아직 작성한 포스트가 없습니다.</p>}
      {sortedPosts.map((item, index) => {
        const [title, image, data] = item
        const authorName = String(data?.author_display_name || user?.user_metadata?.display_name || 'FANHEAT').trim().replace(/^@/, '')
        const authorId = authorName.replace(/\s+/g, '_')
        return <article key={data?.id || `${title}-${index}`} onClick={() => onSelect({ title, image, index, data })} tabIndex="0">
          <span className="my-post-rank">{index + 1}<i>•••</i></span><MyPostListThumbnail title={title} image={image} data={data} />
          <div className="my-post-copy">{title && <h3>{title}</h3>}{data?.summary && <p>{data.summary}</p>}<PostMetadata className="my-post-meta" viewCount={data?.view_count || 0} giftCount={data?.gift_count || 0} commentCount={data?.comment_count || 0} authorId={authorId} /></div>
          <time>{new Date(data?.created_at || Date.now()).toLocaleDateString('ko-KR')}</time>
          <HeatVote initialCount={data?.vote_count ?? 0} />
        </article>
      })}
      <footer className="my-board-footer my-board-footer-summary"><span>Total <b>{filteredPosts.length}</b></span></footer>
    </div>}
  </section>
}

function Awards({ items = [], rankings = {}, onSelect, onViewAll }) {
  const { locale, t } = useI18n()
  const [period, setPeriod] = useState('Today')
  const [page, setPage] = useState(0)
  const [pageCount, setPageCount] = useState(2)
  const [paused, setPaused] = useState(false)
  const track = useRef(null)
  const periodKey = { Today: 'today', Weeks: 'week', Month: 'month' }[period]
  const popularityTitle = ({
    ko: { today: '오늘 인기 아티스트', week: '주간 인기 아티스트', month: '월간 인기 아티스트' },
    en: { today: "Today's Popular Artists", week: 'Weekly Popular Artists', month: 'Monthly Popular Artists' },
    ja: { today: '今日の人気アーティスト', week: '週間人気アーティスト', month: '月間人気アーティスト' },
  }[locale] || {})[periodKey] || t('awards')
  const periodMetrics = rankings[periodKey] || []
  const metricByArtist = new Map(periodMetrics.map(metric => [String(metric.artist_id), metric]))
  const sourceItems = items.slice(0, 50)
  const sortedEntries = sourceItems
    .map((item, originalIndex) => ({
      item,
      originalIndex,
      metric: metricByArtist.get(String(item[3]?.id)),
      fallbackScore: Number(item[3]?.score ?? String(item[1] || '').replace(/,/g, '')) || 0,
    }))
    .sort((a, b) => {
      const aScore = Number(a.metric?.ranking_score ?? a.fallbackScore)
      const bScore = Number(b.metric?.ranking_score ?? b.fallbackScore)
      return bScore - aScore || a.originalIndex - b.originalIndex
    })
  const rankedItems = sortedEntries.map((entry, index, entries) => {
    const score = Number(entry.metric?.ranking_score ?? entry.fallbackScore)
    const previousScore = index ? Number(entries[index - 1].metric?.ranking_score ?? entries[index - 1].fallbackScore) : null
    const previousRank = index ? Number(entries[index - 1].computedRank) : 1
    entry.computedRank = index && score === previousScore ? previousRank : index ? previousRank + 1 : 1
    const clicks = Number(entry.metric?.click_count || 0)
    const fans = Number(entry.metric?.fan_growth || 0)
    return { ...entry, rank: entry.computedRank, change: 0, score: score.toLocaleString('ko-KR'), activity: `클릭 ${clicks.toLocaleString('ko-KR')} · 팬 +${fans.toLocaleString('ko-KR')}` }
  })
  const measure = () => {
    if (!track.current) return
    const card = track.current.querySelector('article')
    if (!card) return
    const gap = 8
    const visible = Math.max(1, Math.floor((track.current.clientWidth + gap) / (card.getBoundingClientRect().width + gap)))
    setPageCount(Math.max(1, Math.ceil(rankedItems.length / visible)))
  }
  const goTo = target => {
    const next = (target + pageCount) % pageCount
    setPage(next)
    if (!track.current) return
    const cards = [...track.current.querySelectorAll('article')]
    const card = cards[0]
    const gap = 8
    const visible = card ? Math.max(1, Math.floor((track.current.clientWidth + gap) / (card.getBoundingClientRect().width + gap))) : 1
    const firstCard = cards[next * visible]
    track.current.scrollTo({ left: firstCard?.offsetLeft || 0, behavior: 'smooth' })
  }
  useEffect(() => {
    measure()
    const observer = new ResizeObserver(measure)
    if (track.current) observer.observe(track.current)
    return () => observer.disconnect()
  }, [rankedItems.length])
  useEffect(() => {
    if (paused || pageCount < 2) return undefined
    const timer = setInterval(() => goTo(page + 1), 4500)
    return () => clearInterval(timer)
  }, [page, pageCount, paused])
  useEffect(() => {
    setPage(0)
    track.current?.scrollTo({ left: 0, behavior: 'smooth' })
  }, [period])
  return <section className="awards" id="awards">
    <div className="section-head"><div className="section-title"><h2>{popularityTitle}</h2><button className="view-all-artists" onClick={onViewAll}>{({ ko: '전체', en: 'All', ja: 'すべて' })[locale] || '전체'} <span>›</span></button></div>
      <div className="periods">{[['Today','today'], ['Weeks','weeks'], ['Month','month']].map(([item,key]) => <button className={period === item ? 'active' : ''} onClick={() => setPeriod(item)} key={item}>{t(key)}</button>)}</div>
    </div>
    <div className="award-carousel" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <button className="award-arrow prev" onClick={() => goTo(page - 1)} aria-label="이전 어워즈">‹</button>
      <div className="award-grid" ref={track}>{rankedItems.map(({ item, originalIndex, rank, activity }) => { const [name, , image] = item; const trendLabel = '원데이 투표와 별개인 클릭·팬 활동 기준'; return <article key={`${period}-${name}-${originalIndex}`}>
        <button className="award-card" onClick={() => { recordArtistClick(item[3]?.id).catch(() => {}); onSelect?.(makeStarProfile(item)) }} aria-label={`${name}, ${rank}위, ${trendLabel}`}>
          <span className="award-image"><img src={assetSrc(image)} alt={name} /></span>
          <span className="award-caption"><strong><i>{rank}위</i> {name}</strong><small>{activity}</small><em className="rank-change same" title={trendLabel}>—</em></span>
        </button>
      </article> })}</div>
      <button className="award-arrow next" onClick={() => goTo(page + 1)} aria-label="다음 어워즈">›</button>
    </div>
    <div className="award-dots" aria-label="어워즈 페이지">{Array.from({ length: pageCount }, (_, index) => <button key={index} className={page === index ? 'active' : ''} onClick={() => goTo(index)} aria-label={`${index + 1}페이지`} />)}</div>
  </section>
}

function ArtistDirectory({ items, query, setQuery, onSelect }) {
  const keyword = query.trim().toLowerCase()
  const visible = items.filter(([name, , , data]) => `${name} ${data?.name || ''}`.toLowerCase().includes(keyword))
  return <section className="artist-directory">
    <header className="artist-directory-head">
      <div><h1>좋아하는 아티스트를 발견하고,<br />팬들과 더 가까워지는 곳.</h1><p>FAN HEAT에서 새로운 스타와 음악, 그리고 팬들의 이야기를 만나보세요.</p></div>
    </header>
    <label className="artist-directory-search"><span>⌕</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="가수 또는 그룹 검색" aria-label="아티스트 검색" />{query && <button onClick={() => setQuery('')} aria-label="검색어 지우기">×</button>}</label>
    <div className="artist-directory-grid">
      {visible.map((item, index) => { const [name, score, image, data] = item; const originalIndex = items.indexOf(item); const hasMaster = Boolean(data?.master_user_id || data?.master_id || data?.has_master || [0, 3, 6, 9].includes(originalIndex)); const topTracks = catalogTopTracks(data, name); return <button className={`artist-directory-card artist-palette-${originalIndex % 8}`} key={data?.id || `${name}-${index}`} onClick={() => onSelect(makeStarProfile(item))}>
        <span className="artist-card-top"><b>★ FAN HEAT</b><small>ARTIST PAGE</small><i>{String(originalIndex + 1).padStart(2, '0')}</i></span>
        <span className="artist-card-body">
          <span className="artist-card-left"><span className="artist-directory-image"><img src={assetSrc(image)} alt={name} /></span><span className="artist-card-stat"><small>FANS</small><strong>{score === 'FAN HEAT' ? 'OFFICIAL' : score}</strong></span><span className="artist-card-genre"><small>GENRE</small><strong>K-POP</strong></span></span>
          <span className="artist-directory-copy"><span className="artist-card-heading">TOP ARTIST</span><span className="artist-directory-name"><strong>{name}</strong>{hasMaster && <span className="artist-master-badge" title="FAN HEAT 관리자에게 승인된 아티스트 마스터"><i aria-hidden="true">◆</i> MASTER</span>}</span><small>{data?.name && data.name !== name ? data.name : 'K-POP ARTIST'}</small><span className="artist-card-label">TOP TRACKS</span><ol className="artist-top-tracks">{topTracks.map((track, trackIndex) => <li key={track}><b>{String(trackIndex + 1).padStart(2, '0')}</b><span>{track}</span></li>)}</ol></span>
        </span>
        <b className="artist-card-open" aria-hidden="true">↗</b>
      </button> })}
    </div>
    {!visible.length && <div className="artist-directory-empty"><strong>검색 결과가 없습니다.</strong><span>다른 가수명이나 그룹명으로 검색해 보세요.</span></div>}
  </section>
}

function useArtistEngagement(star, user, onLogin) {
  const [following, setFollowing] = useState(false)
  const [followerCount, setFollowerCount] = useState(Number(star.followers || 0))
  const [fan, setFan] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    setFollowerCount(Number(star.followers || 0)); setFollowing(false); setFan(null); setError('')
    if (!user?.id || !star.id) return undefined
    loadArtistEngagement(user.id, star.id).then(result => { if (active) { setFollowing(result.following); setFan(result.fan) } }).catch(loadError => { if (active) setError(loadError.message) })
    return () => { active = false }
  }, [star.id, star.followers, user?.id])
  useEffect(() => {
    const sync = event => {
      if (Number(event.detail?.artistId) !== Number(star.id)) return
      if (typeof event.detail.following === 'boolean') setFollowing(event.detail.following)
      if (Number.isFinite(event.detail.followerCount)) setFollowerCount(event.detail.followerCount)
    }
    window.addEventListener('fanheat:artist-engagement', sync)
    return () => window.removeEventListener('fanheat:artist-engagement', sync)
  }, [star.id])
  const toggleFollowing = async () => {
    if (!user) { onLogin(); return }
    const next = !following
    setBusy('follow'); setError('')
    try {
      await setArtistFollowing(user.id, star.id, next)
      const nextCount = Math.max(0, followerCount + (next ? 1 : -1))
      setFollowing(next); setFollowerCount(nextCount)
      window.dispatchEvent(new CustomEvent('fanheat:artist-engagement', { detail: { artistId: star.id, following: next, followerCount: nextCount } }))
    } catch (toggleError) { setError(toggleError.message) }
    finally { setBusy('') }
  }
  const toggleFan = async () => {
    if (!user) { onLogin(); return null }
    setBusy('fan'); setError('')
    try {
      const nextFan = await setArtistFanRegistration(user.id, star.id, !fan)
      setFan(nextFan)
      return nextFan
    } catch (toggleError) { setError(toggleError.message); return undefined }
    finally { setBusy('') }
  }
  return { following, followerCount, fan, busy, error, toggleFollowing, toggleFan }
}

const artistSocialChannels = [
  ['facebookUrl', 'facebook', 'Facebook'],
  ['xUrl', 'twitter', 'X'],
  ['instagramUrl', 'instagram', 'Instagram'],
]

const safeArtistSocialUrl = value => {
  try {
    const parsed = new URL(String(value || '').trim())
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : ''
  } catch {
    return ''
  }
}

function ArtistSocialIcon({ type }) {
  if (type === 'facebook') return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 8h3V4h-3c-3.3 0-5 2-5 5v2H6v4h3v9h4v-9h3l1-4h-4V9c0-.7.3-1 1-1Z" /></svg>
  if (type === 'instagram') return <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5" /><circle cx="12" cy="12" r="4.2" /><circle cx="17.5" cy="6.7" r="1" className="instagram-dot" /></svg>
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.9 2H22l-6.8 7.8L23.2 22H17l-4.8-6.3L6.7 22H3.6l7.1-8.2L3 2h6.3l4.4 5.8L18.9 2Zm-1.1 17.8h1.7L8.3 4.1H6.5l11.3 15.7Z" /></svg>
}

function ArtistSocialLinks({ star, mobile = false }) {
  return <div className={mobile ? 'star-mobile-socials' : 'star-socials'} aria-label="아티스트 공식 소셜 채널">
    {artistSocialChannels.map(([field, type, label]) => {
      const url = safeArtistSocialUrl(star[field])
      const icon = <ArtistSocialIcon type={type} />
      return url
        ? <a className={type} href={url} target="_blank" rel="noopener noreferrer" aria-label={`${star.name} 공식 ${label} 열기`} title={`${label} 공식 채널`} key={field}>{icon}</a>
        : <span className={`${type} is-unavailable`} role="img" aria-label={`${star.name} 공식 ${label} 정보 없음`} aria-disabled="true" title={`${label} 공식 채널 정보 없음`} key={field}>{icon}</span>
    })}
  </div>
}

function StarVisual({ star, onClose, user, onLogin }) {
  const engagement = useArtistEngagement(star, user, onLogin)
  const profileImages = [...new Set((star.profileImages?.length ? star.profileImages : [star.image]).filter(Boolean))]
  if (!profileImages.length) profileImages.push('/images/icon_member.png')
  const [profileSlide, setProfileSlide] = useState(0)
  const [profileDirection, setProfileDirection] = useState('next')
  useEffect(() => { setProfileSlide(0) }, [star.id])
  const showProfileSlide = (next, direction = 'next') => { setProfileDirection(direction); setProfileSlide(next) }
  const profileSwipe = useSwipeCarousel({ length: profileImages.length, index: profileSlide, onChange: showProfileSlide, threshold: 24 })
  return <section className="star-visual" aria-label={`${star.name} 프로필`}>
    <aside className="star-profile">
      <button className="star-back" onClick={onClose} aria-label="메인으로 돌아가기">‹</button>
      <button className={`star-like ${engagement.following ? 'active' : ''}`} onClick={engagement.toggleFollowing} disabled={engagement.busy === 'follow'} aria-pressed={engagement.following} aria-label={engagement.following ? `${star.name} 팔로우 취소` : `${star.name} 팔로우`}>♥</button>
      <div className={`star-avatar-carousel ${profileSwipe.dragging ? 'dragging' : ''}`} {...profileSwipe.bind}>
        <img key={`${profileImages[profileSlide]}-${profileSlide}`} className={`star-avatar ${profileDirection}`} style={{ transform: `translateX(${profileSwipe.dragOffset}px)` }} src={assetSrc(profileImages[profileSlide])} alt={`${star.name} 프로필 ${profileSlide + 1}`} draggable="false" />
      </div>
      <div className="star-profile-dots">{profileImages.map((_, index) => <button key={index} className={profileSlide === index ? 'active' : ''} onClick={() => showProfileSlide(index, index >= profileSlide ? 'next' : 'prev')} aria-label={`${index + 1}번째 프로필 이미지`} />)}</div>
      <div className="star-facts"><small>PROFILE</small><h1>{star.realName}</h1><p>{star.role}</p><dl><div><dt>데뷔</dt><dd>{star.debut}</dd></div><div><dt>소속사</dt><dd>{star.agency}</dd></div><div><dt>팬덤</dt><dd>{star.fandom}</dd></div></dl></div>
      <div className="star-followers"><small>FOLLOWER</small><strong>{engagement.followerCount.toLocaleString()}</strong><span>명</span>{engagement.error && <em role="alert">{engagement.error}</em>}</div>
      <div className="star-visitors"><small>VISITOR</small><p>Today : {(star.visitorToday || 454842).toLocaleString()}</p><p>Total : {(star.visitorTotal || 405541258).toLocaleString()}</p></div>
      <ArtistSocialLinks star={star} />
    </aside>
    <div className="star-portrait"><img src={assetSrc(star.heroImage || star.image)} alt={`${star.name} 고해상도 대표 이미지`} />{star.imageCredit && <a className="star-image-credit" href={star.imageCreditUrl} target="_blank" rel="noreferrer">Photo: {star.imageCredit}</a>}</div>
  </section>
}

function AlbumDetailModal({ star, album, onClose }) {
  const tracks = [...(album.trackItems || [])].sort((a, b) => Number(a.display_order || a.track_number) - Number(b.display_order || b.track_number))
  const [selectedTrackId, setSelectedTrackId] = useState(null)
  const featuredTrack = tracks.find(track => track.id === selectedTrackId) || tracks.find(track => youtubeEmbedUrl(track.youtube_url)) || tracks[0]
  const videoUrl = featuredTrack ? featuredTrack.youtube_url : album.youtubeUrl
  const embedUrl = youtubeEmbedUrl(videoUrl)
  const externalUrl = album.externalUrl || `https://www.melon.com/search/total/index.htm?q=${encodeURIComponent(`${star.name} ${album.title}`)}`

  useEffect(() => {
    const closeOnEscape = event => { if (event.key === 'Escape') onClose() }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  return createPortal(<div className="album-modal-overlay" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <section className="album-modal" role="dialog" aria-modal="true" aria-labelledby="album-modal-title">
      <header className="album-modal-head">
        <strong>K-POP Music</strong>
        <div>
          <a className="melon-buy" href={externalUrl} target="_blank" rel="noreferrer"><span>앨범 정보</span><b>OPEN</b></a>
          <button className="album-modal-close" onClick={onClose} aria-label="앨범 상세 닫기">×</button>
        </div>
      </header>
      <div className="album-modal-grid">
        <div className="album-modal-left">
          <h2 id="album-modal-title">{star.name} · {album.title}</h2>
          <div className="album-summary">
            <img src={assetSrc(album.image)} alt={`${album.title} 앨범 재킷`} />
            <div><h3>{album.title}</h3><dl><div><dt>발매일</dt><dd>{album.date || '미등록'}</dd></div><div><dt>앨범</dt><dd>{album.type}</dd></div><div><dt>곡수</dt><dd>{tracks.length || album.tracks}곡</dd></div><div><dt>아티스트</dt><dd>{star.name}</dd></div><div><dt>장르</dt><dd>{album.genre || '미등록'}</dd></div><div><dt>레이블</dt><dd>{album.label || '미등록'}</dd></div></dl></div>
          </div>
          {album.description && <p className="album-db-description">{album.description}</p>}
          <h3 className="album-subtitle">곡 정보</h3>
          <div className="track-table" role="table" aria-label={`${album.title} 수록곡`}>
            <div className="track-table-head" role="row"><span>번호</span><span>곡 정보</span><span>시간</span><span>영상</span></div>
            {tracks.map(track => <div className="track-row" role="row" key={track.id}><span>{track.track_number}</span><strong><button type="button" className="album-track-select" aria-pressed={featuredTrack?.id === track.id} onClick={() => setSelectedTrackId(track.id)}>{track.title}</button>{track.title === album.track && <em>TITLE</em>}</strong><span>{track.duration_text || '—'}</span>{track.youtube_url ? <a href={track.youtube_url} target="_blank" rel="noreferrer" aria-label={`${track.title} YouTube에서 보기`}>▶</a> : <span>—</span>}</div>)}
            {!tracks.length && <p className="album-db-empty">등록된 수록곡이 없습니다.</p>}
          </div>
        </div>
        <div className="album-modal-right">
          <div className="album-video-title"><h3>{featuredTrack?.title || album.track}</h3><span>YouTube</span></div>
          <div className="album-video-frame">{embedUrl ? <iframe key={embedUrl} src={embedUrl} referrerPolicy="strict-origin-when-cross-origin" title={`${star.name} ${featuredTrack?.title || album.track} 영상`} allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowFullScreen /> : <div className="album-db-empty">이 곡에 연결된 공식 YouTube 영상이 아직 없습니다.</div>}</div>
          {embedUrl && <a className="album-youtube-external" href={videoUrl} target="_blank" rel="noopener noreferrer">재생이 제한되면 YouTube에서 보기 ↗</a>}<div className="album-lyrics-title"><h3>곡 소개</h3><span>TRACK NOTE</span></div>
          <div className="album-lyrics">{featuredTrack?.lyrics_excerpt ? <p>{featuredTrack.lyrics_excerpt}</p> : <p>등록된 곡 소개가 없습니다.</p>}</div>
        </div>
      </div>
    </section>
  </div>, document.body)
}

function StarAlbums({ star }) {
  const [visibleCount, setVisibleCount] = useState(8)
  const [selectedAlbum, setSelectedAlbum] = useState(null)
  const sentinel = useRef(null)
  const catalog = (star.albums || []).filter(album => album.active !== false).map(album => ({ id: album.id, title: album.title, track: album.lead_track || album.title, date: album.release_date?.replaceAll('-', '.') || '', type: album.album_type || '앨범', tracks: Number(album.track_count || 0), image: album.cover_url || star.image, youtubeUrl: album.youtube_url || '', description: album.description || '', label: album.label || '', genre: album.genre || '', externalUrl: album.external_url || '', trackItems: (album.artist_album_tracks || []).filter(track => track.active !== false) }))
  const visible = catalog.slice(0, visibleCount)
  useEffect(() => setVisibleCount(8), [star.id])
  useEffect(() => {
    const node = sentinel.current
    if (!node || visibleCount >= catalog.length) return undefined
    const observer = new IntersectionObserver(entries => { if (entries[0]?.isIntersecting) setVisibleCount(count => Math.min(count + 8, catalog.length)) }, { rootMargin: '180px' })
    observer.observe(node)
    return () => observer.disconnect()
  }, [visibleCount, catalog.length])
  return <section className="star-album-section">
    <div className="star-albums">{visible.map(album => <article key={album.id} role="button" tabIndex="0" aria-label={`${album.title} 상세 보기`} onClick={() => setSelectedAlbum(album)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedAlbum(album) } }}><div className="album-jacket"><img src={assetSrc(album.image)} alt={`${album.title} 앨범 재킷`} /><button onClick={event => { event.stopPropagation(); setSelectedAlbum(album) }} aria-label={`${album.track} 상세 및 영상 보기`}>▶</button></div><h3>{album.title}</h3><p><i>▷</i>{album.track}</p><span>{album.date}　|　{album.type}　|　{album.tracks}곡</span></article>)}</div>
    {!catalog.length && <p className="star-gallery-empty">공개된 앨범이 없습니다.</p>}
    <div className="album-sentinel" ref={sentinel}>{visibleCount < catalog.length ? <span>앨범을 더 불러오는 중…</span> : catalog.length > 8 ? <span>모든 앨범을 확인했습니다.</span> : null}</div>
    {selectedAlbum && <AlbumDetailModal star={star} album={selectedAlbum} onClose={() => setSelectedAlbum(null)} />}
  </section>
}

const starGalleryCardCopy = [
  ['무대 위 빛나는 순간', '2026.08.24'],
  ['공연 비하인드', '2026.08.18'],
  ['팬들과 함께한 하루', '2026.08.09'],
  ['새 앨범 콘셉트 포토', '2026.07.28'],
  ['오늘의 활동 스케치', '2026.07.17'],
  ['백스테이지에서', '2026.07.05'],
  ['여름 페스티벌 현장', '2026.06.22'],
  ['팬미팅 포토', '2026.06.11'],
  ['뮤직비디오 촬영 현장', '2026.05.30'],
  ['시상식 레드카펫', '2026.05.18'],
  ['컴백 쇼케이스', '2026.05.06'],
  ['연습실 비하인드', '2026.04.24'],
]

function StarGallery({ star }) {
  const [periodMonths, setPeriodMonths] = useState('all')
  const [visibleCount, setVisibleCount] = useState(10)
  const [lightboxIndex, setLightboxIndex] = useState(null)
  const sentinel = useRef(null)
  const galleryItems = (star.galleryItems || []).filter(isApprovedArtistGalleryItem).map(item => ({ image: item.image_url, title: item.title, date: item.captured_on?.replaceAll('-', '.') || '', timestamp: item.captured_on ? new Date(`${item.captured_on}T00:00:00`).getTime() : Date.now(), creator: item.creator_name || '', license: item.license_name || '', licenseUrl: item.license_url || '', sourceUrl: item.source_page_url || '', attribution: item.attribution_text || '' }))
  const periodStart = periodMonths === 'all' ? null : new Date()
  periodStart?.setMonth(periodStart.getMonth() - periodMonths)
  const filteredItems = periodStart ? galleryItems.filter(item => item.timestamp >= periodStart.getTime()) : galleryItems
  const visibleItems = filteredItems.slice(0, visibleCount)
  const lightboxImages = visibleItems.map((item, index) => ({
    type: 'image',
    src: item.image,
    imageIndex: index,
    sourceLabel: item.attribution || item.creator || '',
    sourceUrl: item.sourceUrl,
    sourceActionLabel: '출처 바로가기',
    licenseLabel: item.license,
    licenseUrl: item.licenseUrl,
  }))
  useEffect(() => {
    setLightboxIndex(null)
    setVisibleCount(10)
  }, [star.id, periodMonths])
  useEffect(() => {
    const node = sentinel.current
    if (!node || visibleCount >= filteredItems.length) return undefined
    const observer = new IntersectionObserver(entries => {
      if (entries[0]?.isIntersecting) setVisibleCount(count => Math.min(count + 10, filteredItems.length))
    }, { rootMargin: '240px' })
    observer.observe(node)
    return () => observer.disconnect()
  }, [visibleCount, filteredItems.length])
  return <section className="star-gallery-section">
    <div className="star-gallery-toolbar">
      <div className="star-gallery-periods" role="tablist" aria-label="갤러리 조회 기간">{['all', 3, 6, 12].map(period => <button type="button" role="tab" aria-selected={periodMonths === period} className={periodMonths === period ? 'active' : ''} onClick={() => setPeriodMonths(period)} key={period}>{period === 'all' ? 'All' : `${period} Months`}</button>)}</div>
      <span>{filteredItems.length} PHOTOS</span>
    </div>
    <div className="star-gallery-grid">
      {visibleItems.map(({ image, title, date }, index) => {
        return <article className="star-gallery-card" key={`${image}-${index}`}>
          <button className="star-gallery-image" type="button" onClick={() => setLightboxIndex(index)} aria-label={`${star.name} 갤러리 ${index + 1}번째 이미지 크게 보기`}><img src={assetSrc(image)} alt={`${star.name} 갤러리 ${index + 1}번째 이미지`} loading="lazy" /><span aria-hidden="true">크게 보기</span></button>
          {date && <time dateTime={date.replaceAll('.', '-')}>{date}</time>}
        </article>
      })}
    </div>
    {!filteredItems.length && <p className="star-gallery-empty">선택한 기간에 등록된 사진이 없습니다.</p>}
    <div className="star-gallery-sentinel" ref={sentinel} aria-live="polite">{visibleCount < filteredItems.length ? <span>이미지를 더 불러오는 중…</span> : filteredItems.length > 10 ? <span>모든 이미지를 확인했습니다.</span> : null}</div>
    {visibleItems.some(item => item.attribution) && <details className="star-gallery-credits"><summary><span>IMAGE CREDITS</span><small>{visibleItems.filter(item => item.attribution).length}개 이미지</small></summary><div className="star-gallery-credit-panel"><ul>{visibleItems.filter(item => item.attribution).map((item, index) => <li key={`${item.image}-credit`}><span>{index + 1}. {item.attribution}</span><nav aria-label={`${index + 1}번째 이미지 크레딧 링크`}>{item.sourceUrl && <a href={item.sourceUrl} target="_blank" rel="noopener noreferrer">출처</a>}{item.licenseUrl && <a href={item.licenseUrl} target="_blank" rel="noopener noreferrer">라이선스</a>}</nav></li>)}</ul></div></details>}
    {lightboxIndex !== null && <ImageLightbox images={lightboxImages} initialIndex={lightboxIndex} title={`${star.name} 갤러리`} onClose={() => setLightboxIndex(null)} />}
  </section>
}

function StarMobileOverview({ star, engagement }) {
  const profileImages = (star.profileImages?.length ? star.profileImages : [star.image || '/images/icon_member.png']).slice(0, 10)
  const [profileSlide, setProfileSlide] = useState(0)
  useEffect(() => { setProfileSlide(0) }, [star.id])
  const profileSwipe = useSwipeCarousel({ length: profileImages.length, index: profileSlide, onChange: setProfileSlide, threshold: 24 })
  const profileImage = profileImages[profileSlide] || star.image
  return <article className="star-mobile-overview">
    <section className="star-mobile-identity">
      <div className="star-mobile-cover"><img src={assetSrc(star.heroImage || star.image)} alt="" /><button type="button" className={engagement.following ? 'active' : ''} onClick={engagement.toggleFollowing} disabled={engagement.busy === 'follow'} aria-pressed={engagement.following} aria-label={engagement.following ? `${star.name} 팔로우 취소` : `${star.name} 팔로우`}>♥</button></div>
      <div className={`star-mobile-avatar ${profileSwipe.dragging ? 'dragging' : ''}`} {...profileSwipe.bind}><img src={assetSrc(profileImage)} style={{ transform: `translateX(${profileSwipe.dragOffset}px)` }} alt={`${star.name} 프로필`} draggable="false" /></div>
      {profileImages.length > 1 && <div className="star-mobile-profile-dots" aria-label="프로필 이미지 선택">{profileImages.map((image, index) => <button type="button" className={profileSlide === index ? 'active' : ''} onClick={() => setProfileSlide(index)} aria-label={`${index + 1}번째 프로필 이미지`} key={`${image}-${index}`} />)}</div>}
      <div className="star-mobile-name"><small>ARTIST PROFILE</small><h2>{star.realName || star.name}</h2><p>{star.role}</p></div>
      <dl className="star-mobile-facts"><div><dt>데뷔</dt><dd>{star.debut}</dd></div><div><dt>소속사</dt><dd>{star.agency}</dd></div><div><dt>팬덤</dt><dd>{star.fandom}</dd></div></dl>
      <div className="star-mobile-stats"><section><small>FOLLOWERS</small><strong>{engagement.followerCount.toLocaleString()}</strong><span>명</span></section><section><small>VISITORS</small><p><span>오늘</span><b>{Number(star.visitorToday || 0).toLocaleString()}</b></p><p><span>전체</span><b>{Number(star.visitorTotal || 0).toLocaleString()}</b></p></section></div>
      <ArtistSocialLinks star={star} mobile />
    </section>
    <section className="star-mobile-bio"><header><small>ABOUT</small><h3>{star.name} 소개</h3></header>{star.bio.map(paragraph => <p key={paragraph}>{paragraph}</p>)}{!star.bio.length && <p className="star-gallery-empty">등록된 소개가 없습니다.</p>}</section>
    <div className="star-mobile-records"><section><header><small>TIMELINE</small><h3>HISTORY</h3></header><ul>{star.history.map((item, index) => <li key={`${item.year}-${item.text}-${index}`}><time>{item.year}</time><span>{item.text}</span></li>)}</ul>{!star.history.length && <p className="star-gallery-empty">등록된 연혁이 없습니다.</p>}</section><section><header><small>HONORS</small><h3>AWARD</h3></header><ul>{star.awards.map((item, index) => <li key={`${item.year}-${item.text}-${index}`}><time>{item.year}</time><span>{item.text}</span></li>)}</ul>{!star.awards.length && <p className="star-gallery-empty">등록된 수상 정보가 없습니다.</p>}</section></div>
  </article>
}

function StarPage({ star, onOpenFan, onClose, user, onLogin }) {
  const engagement = useArtistEngagement(star, user, onLogin)
  const [correctionOpen, setCorrectionOpen] = useState(false)
  useEffect(() => setCorrectionOpen(false), [star.id])
  const { locale } = useI18n()
  const [tab, setTab] = useState('intro')
  const [fanQuery, setFanQuery] = useState('')
  const [inviteStatus, setInviteStatus] = useState('')
  const [fanRoster, setFanRoster] = useState(() => dedupeArtistFans(star.fans || []))
  useEffect(() => setFanRoster(dedupeArtistFans(star.fans || [])), [star.id, star.fans])
  useEffect(() => {
    if (!engagement.fan) return
    setFanRoster(current => dedupeArtistFans([...current, engagement.fan]))
  }, [engagement.fan])
  const fanProfiles = fanRoster.map(fan => [fan.display_name, fan.handle, fan.avatar_url || 'mypage.jpg', Number(fan.heat_percent || 0), Boolean(fan.featured_rank), fan.featured_rank])
  const visibleFans = fanProfiles.filter(([name, id]) => `${name} ${id}`.toLowerCase().includes(fanQuery.trim().toLowerCase()))
  const totalFans = fanProfiles.length
  const galleryCount = (star.galleryItems || []).filter(isApprovedArtistGalleryItem).length
  const inviteFans = async () => {
    const invite = { title: `${star.name} FAN HEAT`, text: `${star.name} 팬 커뮤니티에 함께해요!`, url: window.location.href }
    try {
      if (navigator.share) await navigator.share(invite)
      else { await navigator.clipboard.writeText(`${invite.text} ${invite.url}`); setInviteStatus('초대 링크 복사됨') }
    } catch (error) { if (error.name !== 'AbortError') setInviteStatus('링크를 복사하지 못했습니다') }
  }
  const toggleFanRegistration = async () => {
    const existingProfileId = engagement.fan?.profile_id
    const result = await engagement.toggleFan()
    if (result === undefined) return
    setFanRoster(current => result
      ? dedupeArtistFans([...current, result])
      : current.filter(item => item.profile_id !== existingProfileId))
  }
  useEffect(() => { setFanQuery(''); setInviteStatus('') }, [star.id])
  const labels = { ko: ['소개', '앨범', '갤러리'], en: ['About', 'Albums', 'Gallery'], ja: ['紹介', 'アルバム', 'ギャラリー'] }[locale] || ['소개', '앨범', '갤러리']
  const tabs = [['intro', labels[0]], ['albums', labels[1]], ['fans', 'FAN'], ['gallery', labels[2]]]
  return <section className="star-page">
    {correctionOpen && <ArtistCorrectionDialog artist={star} onClose={() => setCorrectionOpen(false)} />}
    <header className="star-navigation">
      <div className="star-mobile-appbar"><button type="button" onClick={onClose} aria-label="아티스트 목록으로 돌아가기"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5-7 7 7 7" /></svg></button><strong>{star.name}</strong></div>
      <div className="star-tab-strip"><nav className="star-tabs" aria-label={`${star.name} 콘텐츠 메뉴`} role="tablist">{tabs.map(([key, label]) => <button type="button" role="tab" key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)} aria-selected={tab === key}>{label}{key === 'albums' && <b aria-label={`앨범 ${(star.albums || []).filter(album => album.active !== false).length}개`}>{(star.albums || []).filter(album => album.active !== false).length}</b>}{key === 'gallery' && <b aria-label={`승인된 갤러리 이미지 ${galleryCount}개`}>{galleryCount}</b>}</button>)}</nav><button type="button" className="star-correction-button" title="아티스트 정보 수정 요청" aria-label="아티스트 정보 수정 요청" disabled={!Number.isInteger(Number(star.id))} onClick={() => user ? setCorrectionOpen(true) : onLogin()}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 5 5 5M4 20l3.5-.8L19 7.7 16.3 5 4.8 16.5 4 20Z" /></svg><span>수정 요청</span></button></div>
    </header>
    {tab === 'intro' && <><StarMobileOverview star={star} engagement={engagement} /><article className="star-introduction"><div className="star-bio">{star.bio.map(paragraph => <p key={paragraph}>{paragraph}</p>)}{!star.bio.length && <p className="star-gallery-empty">Supabase에 등록된 소개가 없습니다.</p>}</div><div className="star-records"><section><h3>HISTORY</h3><ul>{star.history.map((item, index) => <li key={`${item.year}-${item.text}-${index}`}><time>{item.year}</time><span>{item.text}</span></li>)}</ul>{!star.history.length && <p className="star-gallery-empty">등록된 연혁이 없습니다.</p>}</section><section><h3>AWARD</h3><ul>{star.awards.map((item, index) => <li key={`${item.year}-${item.text}-${index}`}><time>{item.year}</time><span>{item.text}</span></li>)}</ul>{!star.awards.length && <p className="star-gallery-empty">등록된 수상 정보가 없습니다.</p>}</section></div></article></>}
    {tab === 'albums' && <StarAlbums star={star} />}
    {tab === 'fans' && <section className="star-fan-board"><header className="star-fan-tools"><label className="star-fan-search"><span aria-hidden="true">⌕</span><input value={fanQuery} onChange={event => setFanQuery(event.target.value)} placeholder="이름 또는 ID로 팬 찾기" aria-label="팬 검색" />{fanQuery && <button type="button" onClick={() => setFanQuery('')} aria-label="팬 검색어 지우기">×</button>}</label><button className="star-fan-invite" type="button" onClick={inviteFans}><span>＋</span> INVITE</button><button className={`star-fan-register ${engagement.fan ? 'active' : ''}`} type="button" onClick={toggleFanRegistration} disabled={engagement.busy === 'fan'}>{engagement.busy === 'fan' ? '처리 중…' : engagement.fan ? '팬 등록 해제' : '팬으로 등록'}</button><div className="star-fan-count"><span>TOTAL</span><strong>{totalFans.toLocaleString()}</strong></div>{inviteStatus && <em>{inviteStatus}</em>}{engagement.error && <em className="error" role="alert">{engagement.error}</em>}</header><div className="star-fan-grid">{visibleFans.map(([name, id, image, activity, highlighted, explicitRank]) => { const index = fanProfiles.findIndex(([, fanId]) => fanId === id); const rank = explicitRank || index + 1; const profile = { name, id, image, activity, artist: star.name }; return <article className={highlighted ? 'top-fan' : ''} key={id}><div className={`fan-profile-ring fan-color-${index % 6}`}>{highlighted && <span className={`fan-crown crown-${Math.min(rank, 3)}`} aria-label={`${rank}위 팬`}><svg viewBox="0 0 44 32" aria-hidden="true"><path d="M4 8.5 13.2 16 22 4l8.8 12L40 8.5l-3.2 18H7.2L4 8.5Z" /><path d="M8 27.5h28" /></svg><b>{rank}</b></span>}<img src={assetSrc(image)} alt={`${name} 프로필`} /></div><div className="fan-account"><span>{id}</span><button type="button" onClick={() => onOpenFan(profile)} aria-label={`${id} 소개 페이지로 이동`} title="팬 홈"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 10 8-6 8 6v9a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1v-9Z" /></svg></button></div><div className="fan-activity" aria-label={`HEAT ${activity}%`}><span><b>HEAT</b><em>{activity}%</em></span><i><b style={{ width: `${activity}%` }} /></i></div></article> })}</div>{!visibleFans.length && <div className="star-fan-empty"><strong>찾는 팬이 없습니다.</strong><span>다른 이름이나 ID로 검색해 보세요.</span></div>}</section>}
    {tab === 'gallery' && <StarGallery star={star} />}
  </section>
}

function postListMediaSlides(title, image, data, index) {
  const referenceUrl = data?.reference_url || ''
  const storedImages = Array.isArray(data?.images) ? data.images.filter(Boolean) : []
  const images = storedImages.length ? storedImages : (image ? [image] : [])
  const youtubeUrl = youtubeEmbedUrl(referenceUrl)
  // Collected YouTube previews can already contain pillar-box padding inside
  // the bitmap. Mark them for a tighter square-list crop without affecting
  // ordinary uploaded photos.
  const imageSlides = images.map(src => ({ type: 'image', src, fillCrop: Boolean(youtubeUrl) }))
  const xMatch = referenceUrl.match(/(?:x|twitter)\.com\/([^/]+)\/status\/(\d+)/i)
  const xPost = xMatch ? { type: 'x', id: xMatch[2], url: referenceUrl, account: xMatch[1], handle: `@${xMatch[1]}` } : null
  const facebookUrl = /facebook\.com|fb\.watch/i.test(referenceUrl) ? referenceUrl : ''
  const tiktokId = referenceUrl.match(/\/video\/(\d+)/)?.[1]
  const tiktokUrl = tiktokId ? referenceUrl : ''
  const instagramPost = /instagram\.com\/(p|reel)\//i.test(referenceUrl)
  if (facebookUrl) return [{ type: 'facebook', url: facebookUrl, account: 'K-pop Trends', handle: 'Facebook 공개 게시물' }]
  if (tiktokId) return [{ type: 'tiktok', id: tiktokId, url: tiktokUrl, account: 'IVE.official', handle: '@ive.official' }]
  if (instagramPost) return [{ type: 'instagram', url: referenceUrl, account: 'Instagram', handle: '공개 게시물' }]
  if (xPost) return [xPost, ...imageSlides.slice(0, 4)]
  return youtubeUrl ? [...imageSlides.slice(0, 5), { type: 'youtube', src: youtubeUrl, url: referenceUrl }] : imageSlides.slice(0, 5)
}

function PlatformListPlaceholder({ item, direction }) {
  const labels = {
    x: ['𝕏', item?.account || 'X', item?.handle || '공개 게시물', 'X POST'],
    facebook: ['f', item?.account || 'Facebook', item?.handle || '공개 게시물', 'FACEBOOK'],
    instagram: ['◎', item?.account || 'Instagram', item?.handle || '공개 게시물', 'INSTAGRAM'],
    tiktok: ['♪', item?.account || 'TikTok', item?.handle || '공개 게시물', 'TIKTOK'],
    youtube: ['▶', 'YouTube', '영상 썸네일을 불러올 수 없습니다', 'YOUTUBE'],
  }
  const [brand, account, handle, badge] = labels[item?.type] || ['•', '미디어', '', 'MEDIA']
  return <div className={`post-x-thumbnail post-social-thumbnail social-${item?.type} ${direction}`}>
    <span className="post-x-thumbnail-brand" aria-hidden="true">{brand}</span>
    <div><strong>{account}</strong><small>{handle}</small></div>
    <b>{badge}</b>
  </div>
}

function YouTubeListThumbnail({ item, direction, title }) {
  const [attempt, setAttempt] = useState(0)
  useEffect(() => { setAttempt(0) }, [item?.url])
  const qualities = ['maxresdefault', 'sddefault', 'hqdefault', 'mqdefault']
  const thumbnail = attempt < qualities.length ? youtubeThumbnailUrl(item.url, qualities[attempt]) : ''
  if (!thumbnail) return <PlatformListPlaceholder item={{ ...item, type: 'youtube' }} direction={direction} />
  return <div className={`post-youtube-thumbnail ${direction}`}><img src={thumbnail} alt={`${title} YouTube 영상 썸네일`} draggable="false" onError={() => setAttempt(current => Math.min(current + 1, qualities.length))} /></div>
}

function PostMediaPreviewSlide({ item, direction, title, index }) {
  if (item?.type === 'image') return <img key={`${item.src}-${index}`} className={`post-media-current ${item.fillCrop ? 'fill-crop' : ''} ${direction}`} src={assetSrc(item.src)} alt={`${title} ${index + 1}번째 이미지`} draggable="false" />
  if (item?.type === 'youtube') return <YouTubeListThumbnail item={item} direction={direction} title={title} />
  return <PlatformListPlaceholder item={item} direction={direction} />
}

function PostThumbnail({ slides, title }) {
  const visibleSlides = slides.slice(0, 6)
  const [slide, setSlide] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [direction, setDirection] = useState('next')
  const dragStart = useRef(null)
  const suppressClick = useRef(false)
  useEffect(() => { if (slide >= visibleSlides.length) setSlide(0) }, [slide, visibleSlides.length])
  const moveTo = (next, nextDirection = 'next') => {
    setDirection(nextDirection)
    setSlide(next)
  }
  const finishDrag = event => {
    if (dragStart.current === null) return
    const distance = event.clientX - dragStart.current
    if (Math.abs(distance) > 16) {
      suppressClick.current = true
      setSlide(current => {
        const next = distance < 0 ? (current + 1) % visibleSlides.length : (current - 1 + visibleSlides.length) % visibleSlides.length
        setDirection(distance < 0 ? 'next' : 'prev')
        return next
      })
    }
    dragStart.current = null
    setDragging(false)
  }
  return <div
    className={`post-media ${dragging ? 'dragging' : ''}`}
    onPointerDown={event => {
      if (visibleSlides.length < 2) return
      dragStart.current = event.clientX
      setDragging(true)
      event.currentTarget.setPointerCapture(event.pointerId)
    }}
    onPointerUp={finishDrag}
    onPointerCancel={finishDrag}
    onClickCapture={event => {
      if (!suppressClick.current) return
      event.preventDefault()
      event.stopPropagation()
      suppressClick.current = false
    }}
  >
    <div className="post-media-viewport"><PostMediaPreviewSlide item={visibleSlides[slide]} direction={direction} title={title} index={slide} /></div>
    <div className="carousel-dots" aria-label={`${title} 미디어 선택`}>
      {visibleSlides.map((item, index) => <button key={`${item.type}-${item.src || item.id || index}`} className={slide === index ? 'active' : ''} onClick={event => { event.stopPropagation(); moveTo(index, index >= slide ? 'next' : 'prev') }} aria-label={`${index + 1}번째 ${item.type === 'image' ? '이미지' : `${item.type} 게시물`}`} />)}
    </div>
  </div>
}

const mediaTypeLabel = type => ({ image: '이미지', x: 'X', facebook: 'Facebook', instagram: 'Instagram', tiktok: 'TikTok', youtube: 'YouTube' }[type] || '미디어')

function MediaContent({ item, title, index, expanded = false, dragOffset = 0, onImageClick, youtubePortrait = false, onYoutubeOrientationToggle }) {
  if (item.type === 'x') return <XPostEmbed postId={item.id} postUrl={item.url} />
  if (item.type === 'facebook') return <FacebookPostEmbed postUrl={item.url} />
  if (item.type === 'tiktok') return <TikTokPostEmbed videoId={item.id} postUrl={item.url} />
  if (item.type === 'instagram') return <InstagramPostEmbed embedUrl={item.src} title={title} />
  if (item.type === 'youtube') return <YoutubePostEmbed embedUrl={item.src} title={title} portrait={youtubePortrait} onOrientationToggle={onYoutubeOrientationToggle} />
  return <img
    src={assetSrc(item.src)}
    alt={`${title} ${Number(item.imageIndex ?? index) + 1}번째 이미지`}
    draggable="false"
    onClick={onImageClick}
    title={expanded ? undefined : '클릭하여 크게 보기'}
    style={expanded ? { transform: `translate3d(${dragOffset}px,0,0)` } : undefined}
  />
}

function ImageLightbox({ images, initialIndex, title, onClose }) {
  const [index, setIndex] = useState(initialIndex)
  const [dragOffset, setDragOffset] = useState(0)
  const dragStart = useRef(null)
  const show = next => setIndex((next + images.length) % images.length)
  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKeyDown = event => {
      if (event.key === 'Escape') onClose()
      if (event.key === 'ArrowLeft') setIndex(current => (current - 1 + images.length) % images.length)
      if (event.key === 'ArrowRight') setIndex(current => (current + 1) % images.length)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [images.length, onClose])
  const finishDrag = event => {
    if (dragStart.current === null) return
    const distance = event.clientX - dragStart.current
    if (Math.abs(distance) > 45) show(index + (distance < 0 ? 1 : -1))
    dragStart.current = null
    setDragOffset(0)
  }
  const currentImage = images[index]
  const currentSourceLabel = String(currentImage?.sourceLabel || currentImage?.source_label || currentImage?.label || '').trim()
  const currentSourceUrl = safeExternalUrl(currentImage?.sourceUrl || currentImage?.source_url || currentImage?.url)
  const currentSourceActionLabel = String(currentImage?.sourceActionLabel || '').trim()
  const currentLicenseLabel = String(currentImage?.licenseLabel || currentImage?.license_label || '').trim()
  const currentLicenseUrl = safeExternalUrl(currentImage?.licenseUrl || currentImage?.license_url)
  const hasSource = Boolean(currentSourceUrl)
  const hasLicense = Boolean(currentLicenseLabel || currentLicenseUrl)
  const hasImageDetails = hasSource || hasLicense
  return createPortal(<div className="image-lightbox" role="dialog" aria-modal="true" aria-label={`${title} 이미지 크게 보기`} onClick={onClose}>
    <div className={`image-lightbox-panel ${hasImageDetails ? 'has-source' : ''}`} onClick={event => event.stopPropagation()}>
      <header><strong>{title}</strong><span>사진 {index + 1} / {images.length}</span><button onClick={onClose} aria-label="이미지 팝업 닫기">×</button></header>
      <div className="image-lightbox-stage media-image" onPointerDown={event => { if (event.target.closest('button')) return; dragStart.current = event.clientX; event.currentTarget.setPointerCapture(event.pointerId) }} onPointerMove={event => { if (dragStart.current !== null) setDragOffset(event.clientX - dragStart.current) }} onPointerUp={finishDrag} onPointerCancel={finishDrag}>
        <div className="image-lightbox-media"><MediaContent item={currentImage} title={title} index={index} expanded dragOffset={dragOffset} /></div>
        {images.length > 1 && <><button className="image-lightbox-prev" onClick={() => show(index - 1)} aria-label="이전 이미지">‹</button><button className="image-lightbox-next" onClick={() => show(index + 1)} aria-label="다음 이미지">›</button></>}
      </div>
      {hasImageDetails && <footer className="image-lightbox-source" aria-label="이미지 라이선스 및 출처">
        {hasLicense && <div className="image-lightbox-source-item">{currentLicenseUrl ? <a href={currentLicenseUrl} target="_blank" rel="noopener noreferrer" aria-label={`라이선스 ${currentLicenseLabel || '확인'}`}>{currentLicenseLabel || '라이선스 확인'} <b aria-hidden="true">↗</b></a> : <strong>{currentLicenseLabel}</strong>}</div>}
        {hasSource && <div className="image-lightbox-source-item"><a href={currentSourceUrl} target="_blank" rel="noopener noreferrer" aria-label={`${currentSourceLabel || '이미지'} 출처 바로가기`}>{currentSourceActionLabel || '출처 바로가기'} <b aria-hidden="true">↗</b></a></div>}
      </footer>}
      {images.length > 1 && <div className="image-lightbox-thumbnails" aria-label="확대할 이미지 선택">{images.map((image, imageIndex) => <button key={`${image.src}-${imageIndex}`} className={index === imageIndex ? 'active' : ''} onClick={() => setIndex(imageIndex)} aria-label={`${imageIndex + 1}번째 이미지 보기`}><img src={assetSrc(image.src)} alt="" /></button>)}</div>}
    </div>
  </div>, document.body)
}

const heatTierFor = count => count >= 2000 ? 'viral' : count >= 1000 ? 'mint' : count >= 500 ? 'coral' : count >= 100 ? 'yellow' : 'soft'

function HeatVote({ initialCount, postId, user, onLogin, onCountChange }) {
  const [count, setCount] = useState(initialCount)
  const [voted, setVoted] = useState(false)
  useEffect(() => setCount(Number(initialCount || 0)), [initialCount])
  useEffect(() => {
    let active = true
    if (!postId || !user?.id) { setVoted(false); return undefined }
    loadPostVote(postId, user.id).then(value => { if (active) setVoted(value) }).catch(() => {})
    return () => { active = false }
  }, [postId, user?.id])
  const tier = heatTierFor(count)
  const toggleVote = async event => {
    event.stopPropagation()
    const sessionUser = user || (await supabase?.auth.getSession())?.data?.session?.user
    if (!sessionUser) { onLogin?.(); return }
    const nextVoted = !voted
    try {
      if (postId) await setPostVote(postId, sessionUser.id, nextVoted)
      setVoted(nextVoted)
      const nextCount = count + (nextVoted ? 1 : -1)
      setCount(nextCount)
      onCountChange?.(postId, nextCount)
    } catch { /* Keep the visible count unchanged when persistence fails. */ }
  }
  return <button className={`heat heat-${tier} ${voted ? 'voted' : ''}`} onClick={toggleVote} aria-pressed={voted} aria-label={`이 게시물에 보팅하기, 현재 ${count.toLocaleString()}명`}>
    <span className="heat-star-wrap" aria-hidden="true"><i className="heat-star" />{tier === 'viral' && <em className="heat-badge">HIT</em>}</span>
    <strong>{count.toLocaleString()}명</strong>
  </button>
}

function PostMetaIcon({ type }) {
  const paths = {
    views: <><path d="M2.5 12s3.4-5 9.5-5 9.5 5 9.5 5-3.4 5-9.5 5-9.5-5-9.5-5Z" /><circle cx="12" cy="12" r="2.5" /></>,
    gifts: <><path d="M4 10h16v10H4zM3 7h18v3H3zM12 7v13M12 7H8.7a2.2 2.2 0 1 1 2.1-2.8L12 7Zm0 0h3.3a2.2 2.2 0 1 0-2.1-2.8L12 7Z" /></>,
    comments: <path d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H10l-5 3v-3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" />,
  }
  return <svg className="post-meta-icon" viewBox="0 0 24 24" aria-hidden="true">{paths[type]}</svg>
}

function PostMetadata({ viewCount = 0, giftCount = 0, commentCount = 0, authorId = 'FANHEAT', className = '' }) {
  return <div className={`stats post-meta ${className}`.trim()}>
    <span title="조회수" aria-label={`조회수 ${Number(viewCount).toLocaleString()}`}><PostMetaIcon type="views" />{Number(viewCount).toLocaleString()}</span>
    <span title="선물" aria-label={`선물 ${Number(giftCount).toLocaleString()}개`}><PostMetaIcon type="gifts" />{Number(giftCount).toLocaleString()}</span>
    <span title="댓글" aria-label={`댓글 ${Number(commentCount).toLocaleString()}개`}><PostMetaIcon type="comments" />{Number(commentCount).toLocaleString()}</span>
    <span className="post-meta-author" title="작성자">@{String(authorId).replace(/^@/, '')}</span>
  </div>
}

function relativePostTime(value) {
  const timestamp = new Date(value || Date.now()).getTime()
  const elapsed = Math.max(0, Date.now() - timestamp)
  const minutes = Math.floor(elapsed / 60000)
  if (minutes < 1) return '방금 전'
  if (minutes < 60) return `${minutes}분 전`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}시간 전`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}일 전`
  return new Date(timestamp).toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' })
}

function Feed({ query, filters, onSelect, items = [], user, onLogin, onHeatChange }) {
  const { t, localizeTitle } = useI18n()
  const [visibleCount, setVisibleCount] = useState(10)
  const sentinel = useRef(null)
  const normalizedQuery = query.trim().toLowerCase()
  const shown = items.map((item, originalIndex) => ({ item, originalIndex })).filter(({ item: [title, , data] }) => {
    const author = String(data?.author_display_name || 'FANHEAT').trim()
    const searchable = `${title} ${data?.summary || ''} ${author} ${(data?.tags || []).join(' ')}`.toLowerCase()
    const createdAt = new Date(data?.published_at || data?.created_at || Date.now())
    const from = filters?.from ? new Date(`${filters.from}T00:00:00`) : null
    const to = filters?.to ? new Date(`${filters.to}T23:59:59`) : null
    return (!normalizedQuery || searchable.includes(normalizedQuery)) && (!filters || filters.author === 'all' || author === filters.author) && (!from || createdAt >= from) && (!to || createdAt <= to)
  }).sort((a, b) => filters?.sort === 'comments'
    ? Number(b.item[2]?.comment_count || 0) - Number(a.item[2]?.comment_count || 0)
    : filters?.sort === 'popular'
      ? Number(b.item[2]?.vote_count || 0) - Number(a.item[2]?.vote_count || 0)
      : new Date(b.item[2]?.published_at || b.item[2]?.created_at || 0) - new Date(a.item[2]?.published_at || a.item[2]?.created_at || 0))
  const filterKey = `${normalizedQuery}|${filters?.from || ''}|${filters?.to || ''}|${filters?.author || 'all'}|${filters?.sort || 'latest'}`
  const visiblePosts = shown.slice(0, visibleCount)
  useEffect(() => setVisibleCount(10), [filterKey])
  useEffect(() => {
    const node = sentinel.current
    if (!node || visibleCount >= shown.length || typeof IntersectionObserver === 'undefined') return undefined
    const observer = new IntersectionObserver(entries => { if (entries[0]?.isIntersecting) setVisibleCount(count => Math.min(count + 10, shown.length)) }, { rootMargin: '260px' })
    observer.observe(node)
    return () => observer.disconnect()
  }, [filterKey, shown.length, visibleCount])
  return <section className="feed" id="feed">
    <div className="post-list post-list-mobile-card">{visiblePosts.map(({ item: [title, image, data], originalIndex }, index) => {
      const authorName = String(data?.author_display_name || 'FANHEAT').trim().replace(/^@/, '')
      const authorId = authorName.replace(/\s+/g, '_')
      const authorAvatar = data?.author_avatar_url
      const viewCount = data?.view_count ?? 0
      const giftCount = data?.gift_count ?? 0
      const commentCount = data?.comment_count ?? 0
      return <article className="post" key={data?.id || `${title}-${originalIndex}`} onClick={() => onSelect({ title, image, index: originalIndex, data })} onKeyDown={event => event.key === 'Enter' && onSelect({ title, image, index: originalIndex, data })} tabIndex="0" aria-label={`${title} 상세 보기`}>
      <div className="post-index"><span>{index + 1}</span></div>
      <header className="post-mobile-header"><span className="post-mobile-avatar" aria-hidden="true"><b>{authorName.slice(0, 1).toUpperCase()}</b>{authorAvatar && <img src={assetSrc(authorAvatar)} alt="" onError={event => { event.currentTarget.hidden = true }} />}</span><div><strong>{authorName}</strong><small>@{authorId} · {relativePostTime(data?.published_at || data?.created_at)}</small></div><button type="button" onClick={event => event.stopPropagation()} aria-label="게시물 메뉴">•••</button></header>
      <div className="post-mobile-copy">{title && <h3>{localizeTitle(title)}</h3>}{data?.summary && <p>{data.summary}</p>}</div>
      <PostThumbnail slides={postListMediaSlides(title, image, data, originalIndex)} title={localizeTitle(title)} />
      <div className="post-copy">{title && <h3>{localizeTitle(title)}</h3>}{data?.summary && <p>{data.summary}</p>}<PostMetadata viewCount={viewCount} giftCount={giftCount} commentCount={commentCount} authorId={authorId} /></div>
      <PostMetadata className="post-mobile-actions" viewCount={viewCount} giftCount={giftCount} commentCount={commentCount} authorId={authorId} />
      <HeatVote initialCount={data?.vote_count ?? 0} postId={data?.id} user={user} onLogin={onLogin} onCountChange={onHeatChange} />
    </article>})}</div>
    {!shown.length && <div className="empty">{t('empty')}</div>}
    {shown.length > visibleCount && <div className="feed-sentinel" ref={sentinel}><span>포스트를 더 불러오는 중…</span></div>}
  </section>
}

function DetailAudioPlayer({ post }) {
  const [playing, setPlaying] = useState(false)
  const data = post?.data || {}
  return <UnifiedAudioPlayer track={{ id: data.id, cover: post?.image || 'music1.jpg', title: data.audio_title || '비도 오고 그래서', artist: data.audio_artist || '헤이즈 (Heize)', audioUrl: data.audio_url || '/sample.mp3' }} playing={playing} onPlayingChange={setPlaying} className="post-detail-unified-audio" label="첨부 음원 플레이어" />
}

function XPostEmbed({ postId, postUrl }) {
  return <section className="post-x-embed" aria-label="IVE 공식 X 게시물">
    <header><span className="x-brand" aria-hidden="true">𝕏</span><div><strong>IVE OFFICIAL</strong><small>@IVEstarship · 공식 X 게시물</small></div><a href={postUrl} target="_blank" rel="noreferrer">X에서 보기 ↗</a></header>
    <iframe src={`https://platform.twitter.com/embed/Tweet.html?id=${postId}&theme=light&dnt=true&lang=ko`} title="IVE 공식 X 최근 근황 게시물" loading="lazy" allowFullScreen />
    <p>X의 개인정보 설정이나 네트워크 환경에 따라 게시물이 표시되지 않을 수 있습니다. <a href={postUrl} target="_blank" rel="noreferrer">공식 게시물 열기</a></p>
  </section>
}

function FacebookPostEmbed({ postUrl }) {
  const embedUrl = `https://www.facebook.com/plugins/post.php?href=${encodeURIComponent(postUrl)}&show_text=true&width=500`
  return <section className="post-social-embed post-facebook-embed" aria-label="IVE 관련 Facebook 공개 게시물">
    <header><span className="social-brand" aria-hidden="true">f</span><div><strong>K-pop Trends</strong><small>Facebook · 퍼가기 허용 공개 게시물</small></div><a href={postUrl} target="_blank" rel="noreferrer">Facebook에서 보기 ↗</a></header>
    <iframe src={embedUrl} title="IVE SCOUT Facebook 공개 게시물" loading="lazy" allow="autoplay; clipboard-write; encrypted-media; picture-in-picture; web-share" allowFullScreen />
    <p>Facebook의 쿠키 설정이나 네트워크 환경에 따라 게시물이 표시되지 않을 수 있습니다. <a href={postUrl} target="_blank" rel="noreferrer">공식 게시물 열기</a></p>
  </section>
}

function TikTokPostEmbed({ videoId, postUrl }) {
  return <section className="post-social-embed post-tiktok-embed" aria-label="IVE 틱톡 게시물">
    <header><span className="social-brand" aria-hidden="true">♪</span><div><strong>IVE.official</strong><small>@ive.official · TikTok 공식 영상</small></div><a href={postUrl} target="_blank" rel="noreferrer">TikTok에서 보기 ↗</a></header>
    <iframe src={`https://www.tiktok.com/player/v1/${videoId}?&music_info=1&description=1&autoplay=0&loop=0`} title="IVE 공식 TikTok 영상 게시물" loading="lazy" allow="fullscreen; autoplay; encrypted-media; picture-in-picture" allowFullScreen />
    <p>TikTok의 개인정보 설정이나 네트워크 환경에 따라 영상이 표시되지 않을 수 있습니다. <a href={postUrl} target="_blank" rel="noreferrer">공식 영상 열기</a></p>
  </section>
}

function InstagramPostEmbed({ embedUrl, title }) {
  return <section className="post-social-embed post-instagram-embed" aria-label="Instagram 게시물">
    <header><span className="social-brand" aria-hidden="true">◎</span><div><strong>Instagram</strong><small>대표 미디어</small></div></header>
    <iframe src={embedUrl} title={`${title} Instagram 게시물`} loading="lazy" allow="autoplay; encrypted-media; picture-in-picture" />
  </section>
}

function YoutubePostEmbed({ embedUrl, title, portrait = false, onOrientationToggle }) {
  return <section className="post-youtube" aria-label="YouTube 첨부 영상">
    <header><strong>YouTube</strong><div><button type="button" onClick={onOrientationToggle} aria-label={portrait ? 'YouTube 영상을 가로 프레임으로 보기' : 'YouTube 영상을 세로 프레임으로 보기'}>{portrait ? '가로 맞춤' : '세로 맞춤'}</button><span>첨부 영상</span></div></header>
    <iframe src={embedUrl} title={`${title} YouTube 영상`} loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowFullScreen />
  </section>
}

const relativeCommentTime = date => {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(date).getTime()) / 1000))
  if (seconds < 60) return '방금 전'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}분 전`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}시간 전`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}일 전`
  const months = Math.floor(days / 30)
  if (months < 12) return `${months}개월 전`
  return `${Math.floor(months / 12)}년 전`
}

const commentFromRow = row => ({ id: row.id, authorId: row.author_id, parentId: row.parent_id, avatar: row.author_avatar_url, name: row.author_display_name, createdAt: row.created_at, updatedAt: row.updated_at, text: row.body, likes: Number(row.like_count || 0), dislikes: Number(row.dislike_count || 0), deleted: Boolean(row.deleted_at) })

function CommentAvatar({ comment, user }) {
  const signedInAvatar = comment.authorId === user?.id ? user.user_metadata?.avatar_url : null
  const sources = [...new Set([signedInAvatar, comment.avatar].filter(Boolean))]
  const [sourceIndex, setSourceIndex] = useState(0)
  useEffect(() => setSourceIndex(0), [comment.id, signedInAvatar, comment.avatar])
  const initials = (comment.name || 'FAN').split(' ').map(word => word[0]).join('').slice(0, 2)
  const source = sources[sourceIndex]
  return <div className="avatar">{source ? <img src={assetSrc(source)} alt={`${comment.name} 프로필`} onError={() => setSourceIndex(index => index + 1)} /> : initials}</div>
}

function Comments({ postId, user, onLogin, editCommentId, onOpenAuthor }) {
  const { t } = useI18n()
  const [value, setValue] = useState('')
  const [comments, setComments] = useState([])
  const [error, setError] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [editingValue, setEditingValue] = useState('')
  const [replyingId, setReplyingId] = useState(null)
  const [replyValue, setReplyValue] = useState('')
  const [reactions, setReactions] = useState(new Map())
  const editingForm = useRef(null)
  useEffect(() => {
    if (!postId || !supabase) return
    let active = true
    let loading = false
    const refresh = async () => {
      if (loading || !active) return
      loading = true
      try {
        const rows = await loadComments(postId)
        if (!active) return
        setComments(rows.map(commentFromRow))
        const ownReactions = await loadCommentReactions(user?.id, rows.filter(row => !row.deleted_at).map(row => row.id))
        if (active) {
          setReactions(new Map(ownReactions.map(row => [row.comment_id, row.reaction])))
          setError('')
        }
      } catch (cause) {
        if (active) setError(cause.message)
      } finally {
        loading = false
      }
    }
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') refresh()
    }
    refresh()
    const timer = window.setInterval(refresh, 10000)
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refreshWhenVisible)
    return () => {
      active = false
      window.clearInterval(timer)
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
  }, [postId, user?.id])
  const submit = async event => {
    event.preventDefault()
    if (!value.trim()) return
    if (!user) { onLogin(); return }
    try {
      const row = await addComment(postId, user, value.trim())
      setComments(current => [...current, commentFromRow(row)])
      setValue(''); setError('')
    } catch (cause) { setError(cause.message) }
  }
  const saveEdit = async event => {
    event.preventDefault()
    if (!editingValue.trim() || !user) return
    try {
      const row = await updateComment(editingId, user.id, editingValue)
      setComments(current => current.map(comment => comment.id === editingId ? commentFromRow(row) : comment))
      setEditingId(null); setEditingValue(''); setError('')
    } catch (cause) { setError(cause.message) }
  }
  const submitReply = async event => {
    event.preventDefault()
    if (!replyValue.trim()) return
    if (!user) { onLogin(); return }
    try {
      const row = await addComment(postId, user, replyValue.trim(), replyingId)
      setComments(current => [...current, commentFromRow(row)])
      setReplyingId(null); setReplyValue(''); setError('')
    } catch (cause) { setError(cause.message) }
  }
  const toggleReaction = async (comment, reaction) => {
    if (!user) { onLogin(); return }
    const currentReaction = reactions.get(comment.id)
    const nextReaction = currentReaction === reaction ? null : reaction
    try {
      const counts = await setCommentReaction(comment.id, user.id, nextReaction)
      setReactions(current => { const next = new Map(current); nextReaction ? next.set(comment.id, nextReaction) : next.delete(comment.id); return next })
      setComments(current => current.map(item => item.id === comment.id ? { ...item, ...counts } : item))
    } catch (cause) { setError(cause.message) }
  }
  const removeComment = async comment => {
    if (!user || comment.authorId !== user.id || !window.confirm('이 댓글을 삭제할까요?')) return
    try {
      await deleteComment(comment.id, user.id)
      setComments(current => current.map(item => item.id === comment.id ? { ...item, deleted: true, text: '', name: '삭제된 댓글', avatar: null, likes: 0, dislikes: 0 } : item))
    } catch (cause) { setError(cause.message) }
  }
  const repliesFor = id => comments.filter(comment => comment.parentId === id)
  const hasVisibleBranch = (comment, visited = new Set()) => {
    if (!comment || visited.has(comment.id)) return false
    if (!comment.deleted) return true
    const nextVisited = new Set(visited).add(comment.id)
    return repliesFor(comment.id).some(reply => hasVisibleBranch(reply, nextVisited))
  }
  const roots = comments.filter(comment => !comment.parentId || !comments.some(parent => parent.id === comment.parentId)).filter(comment => hasVisibleBranch(comment))
  const renderComment = (comment, depth = 0, visited = new Set()) => {
    if (visited.has(comment.id) || !hasVisibleBranch(comment)) return null
    const nextVisited = new Set(visited).add(comment.id)
    const children = repliesFor(comment.id).filter(reply => hasVisibleBranch(reply))
    return <article key={comment.id} className={`${depth ? 'comment-reply' : ''} ${comment.deleted ? 'comment-deleted' : ''}`.trim()}>
    {!comment.deleted && <CommentAvatar comment={comment} user={user} />}
    <div className="comment-main">{comment.deleted ? <div className="comment-tombstone"><span>삭제된 댓글입니다.</span></div> : editingId === comment.id ? <form className="comment-edit-form" ref={editingForm} onSubmit={saveEdit}><strong>{comment.name}님의 댓글 수정</strong><textarea value={editingValue} onChange={event => setEditingValue(event.target.value)} maxLength="2000" autoFocus /><div><button type="button" onClick={() => setEditingId(null)}>취소</button><button type="submit" disabled={!editingValue.trim()}>수정 완료</button></div></form> : <>
      <header>{comment.authorId ? <button className="comment-author-profile" type="button" onClick={() => onOpenAuthor?.({ userId: comment.authorId, id: `@${comment.name}`, displayName: comment.name, image: comment.avatar || 'mypage.jpg', artist: 'FANHEAT' })} aria-label={`${comment.name}님의 소개 페이지 열기`}>{comment.name}</button> : <strong>{comment.name}</strong>}<time>{relativeCommentTime(comment.createdAt)}{comment.updatedAt !== comment.createdAt ? ' · 수정됨' : ''}</time></header>
      <p>{comment.text}</p>
      <footer><span className="comment-reactions"><button className={`comment-reaction like ${reactions.get(comment.id) === 'like' ? 'active' : ''}`} onClick={() => toggleReaction(comment, 'like')} aria-label={`좋아요 ${comment.likes}건`} title="좋아요"><span aria-hidden="true">👍</span><b>{comment.likes.toLocaleString()}</b></button><button className={`comment-reaction dislike ${reactions.get(comment.id) === 'dislike' ? 'active' : ''}`} onClick={() => toggleReaction(comment, 'dislike')} aria-label={`싫어요 ${comment.dislikes}건`} title="싫어요"><span aria-hidden="true">👎</span><b>{comment.dislikes.toLocaleString()}</b></button></span><button className="comment-reply-button" onClick={() => { setReplyingId(replyingId === comment.id ? null : comment.id); setReplyValue('') }}>Reply</button>{comment.authorId === user?.id && <span className="comment-owner-actions"><button onClick={() => { setEditingId(comment.id); setEditingValue(comment.text) }}>Edit</button><button onClick={() => removeComment(comment)}>Delete</button></span>}</footer>
      {replyingId === comment.id && <form className="comment-reply-form" onSubmit={submitReply}><textarea value={replyValue} onChange={event => setReplyValue(event.target.value)} maxLength="2000" autoFocus placeholder={`${comment.name}님에게 답글 남기기`} /><div><button type="button" onClick={() => setReplyingId(null)}>취소</button><button type="submit" disabled={!replyValue.trim()}>답글 등록</button></div></form>}
    </>}</div>
    {children.length > 0 && <div className="comment-children">{children.map(reply => renderComment(reply, depth + 1, nextVisited))}</div>}
  </article>
  }
  return <section className="comments">
    <div className="comment-heading"><h3>{t('comments')} {comments.filter(comment => !comment.deleted).length}</h3><span>{t('latest')}</span></div>
    <form className="comment-form" onSubmit={submit}>
      <textarea value={value} onChange={event => setValue(event.target.value)} onFocus={() => !user && onLogin()} readOnly={!user} maxLength="2000" placeholder={user ? t('commentHint') : '댓글을 작성하려면 로그인해 주세요.'} aria-label={t('comments')} />
      <div><span>{2000 - value.length}{t('charsLeft')}</span><button type="submit" disabled={!value.trim()}>{t('submitComment')}</button></div>
    </form>
    {error && <p className="form-error">{error}</p>}
    <div className="comment-list">{roots.map(comment => renderComment(comment))}</div>
  </section>
}

function PostDetail({ post, onClose, user, onLogin, onEdit, previousPost, nextPost, onNavigate, onHeatChange, onOpenAuthor }) {
  const normalizedPost = Array.isArray(post)
    ? { title: post[0] || '', image: post[1] || '', index: 0, data: post[2] || {} }
    : { ...(post || {}), title: post?.title || '', data: post?.data || {} }
  post = normalizedPost
  const { localizeTitle } = useI18n()
  const [slide, setSlide] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [dragOffset, setDragOffset] = useState(0)
  const [lightboxIndex, setLightboxIndex] = useState(null)
  const [isScrolling, setIsScrolling] = useState(false)
  const [heatCount, setHeatCount] = useState(Number(post.data?.vote_count ?? 0))
  const [heated, setHeated] = useState(false)
  const [bookmarked, setBookmarked] = useState(false)
  const [bookmarkPending, setBookmarkPending] = useState(false)
  const [friendStatus, setFriendStatus] = useState('loading')
  const [friendPending, setFriendPending] = useState(false)
  const [friendNotice, setFriendNotice] = useState('')
  const friendNoticeTimer = useRef(null)
  const dragStart = useRef(null)
  const suppressImageClick = useRef(false)
  const scrollHideTimer = useRef(null)
  const detailScrollRoot = useRef(null)
  const referenceUrl = post.data?.reference_url || ''
  const referenceXMatch = referenceUrl.match(/(?:x|twitter)\.com\/[^/]+\/status\/(\d+)/i)
  const iveXPost = referenceXMatch ? { id: referenceXMatch[1], url: referenceUrl } : null
  const iveFacebookPost = /facebook\.com|fb\.watch/.test(referenceUrl) ? { url: referenceUrl } : null
  const referenceTikTokId = referenceUrl.match(/\/video\/(\d+)/)?.[1]
  const iveTikTokPost = referenceTikTokId ? { id: referenceTikTokId, url: referenceUrl } : null
  const instagramEmbedUrl = /instagram\.com\/(p|reel)\//.test(referenceUrl) ? `${referenceUrl.split('?')[0].replace(/\/$/, '')}/embed` : ''
  const youtubeUrl = youtubeEmbedUrl(referenceUrl)
  const youtubeId = youtubeVideoId(referenceUrl)
  const youtubeOrientationKey = youtubeId ? `fanheat-youtube-orientation-v2-${youtubeId}` : ''
  const youtubePortraitHint = /(?:youtube\.com\/shorts\/|#shorts?\b|쇼츠|세로\s*영상|직캠|현장|fan\s*cam|fancam)/i.test(`${referenceUrl} ${post.title || ''} ${post.data?.summary || ''} ${(post.data?.tags || []).join(' ')}`)
  const [youtubePortrait, setYoutubePortrait] = useState(youtubePortraitHint)
  const hasInlineImage = /<img\b/i.test(post.data?.body_html || '')
  const hasInlineMedia = /<(img|iframe)\b|data-youtube-video/i.test(post.data?.body_html || '')
  const storedImages = Array.isArray(post.data?.images) ? post.data.images.filter(Boolean) : []
  const storedImageSources = Array.isArray(post.data?.image_sources) ? post.data.image_sources : []
  const inlineImageSources = Array.isArray(post.data?.inline_image_sources) ? post.data.inline_image_sources : []
  const postSourceUrl = safeExternalUrl(post.data?.source_url || referenceUrl)
  const postSources = Array.isArray(post.data?.source_links) && post.data.source_links.length
    ? post.data.source_links
    : [{ label: post.data?.source_label, url: postSourceUrl }]
  const imageSourceUrls = new Set([...storedImageSources, ...inlineImageSources]
    .map(source => safeExternalUrl(source?.url || source?.source_url))
    .filter(Boolean))
  const articleOnlySources = postSources.filter(source => !imageSourceUrls.has(safeExternalUrl(sourceRowUrl(source))))
  const availableImages = storedImages.length ? storedImages : (post.image ? [post.image] : [])
  const detailImages = hasInlineMedia ? [] : availableImages.slice(0, 5)
  const detailSlides = [
    ...(iveXPost ? [{ type: 'x', id: iveXPost.id, url: iveXPost.url }] : []),
    ...(iveFacebookPost ? [{ type: 'facebook', url: iveFacebookPost.url }] : []),
    ...(iveTikTokPost ? [{ type: 'tiktok', id: iveTikTokPost.id, url: iveTikTokPost.url }] : []),
    ...(instagramEmbedUrl ? [{ type: 'instagram', src: instagramEmbedUrl, url: referenceUrl }] : []),
    ...detailImages.map((src, imageIndex) => {
      const imageSource = storedImageSources[imageIndex] || {}
      return { type: 'image', src, imageIndex, sourceLabel: imageSource.label || imageSource.source_label || '', sourceUrl: imageSource.url || imageSource.source_url || '' }
    }),
    ...(youtubeUrl ? [{ type: 'youtube', src: youtubeUrl, url: referenceUrl }] : []),
  ]
  const detailImageSlides = detailSlides.filter(item => item.type === 'image')
  const activeImageSource = detailSlides[slide]?.type === 'image' ? detailSlides[slide] : null
  const openDetailImage = item => {
    const imageIndex = detailImageSlides.indexOf(item)
    if (imageIndex >= 0) setLightboxIndex(imageIndex)
  }
  const finishDetailDrag = event => {
    if (dragStart.current === null) return
    const distance = event.clientX - dragStart.current
    if (Math.abs(distance) > 35) {
      suppressImageClick.current = true
      setSlide(current => (current + (distance < 0 ? 1 : -1) + detailSlides.length) % detailSlides.length)
      window.setTimeout(() => { suppressImageClick.current = false }, 0)
    }
    dragStart.current = null; setDragOffset(0); setDragging(false)
  }
  useEffect(() => {
    setSlide(0)
    setLightboxIndex(null)
    detailScrollRoot.current?.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }, [post.data?.id, post.title])
  useEffect(() => {
    if (!youtubeId) { setYoutubePortrait(false); return undefined }
    const stored = window.localStorage.getItem(youtubeOrientationKey)
    // Strong portrait metadata (Shorts, 직캠/FANCAM, 현장) must not be hidden by
    // a stale landscape preference saved before those detection rules existed.
    if (youtubePortraitHint) { setYoutubePortrait(true); return undefined }
    if (stored === 'portrait' || stored === 'landscape') { setYoutubePortrait(stored === 'portrait'); return undefined }
    setYoutubePortrait(youtubePortraitHint)
    return undefined
  }, [referenceUrl, youtubeId, youtubeOrientationKey, youtubePortraitHint])
  useEffect(() => setHeatCount(Number(post.data?.vote_count ?? 0)), [post.data?.id, post.data?.vote_count])
  useEffect(() => () => window.clearTimeout(scrollHideTimer.current), [])
  useEffect(() => {
    let active = true
    if (!post.data?.id || !user?.id) { setHeated(false); return undefined }
    loadPostVote(post.data.id, user.id).then(value => { if (active) setHeated(value) }).catch(() => {})
    return () => { active = false }
  }, [post.data?.id, user?.id])
  useEffect(() => {
    let active = true
    if (!post.data?.id || !user?.id) { setBookmarked(false); return undefined }
    loadPostBookmark(post.data.id, user.id).then(value => { if (active) setBookmarked(value) }).catch(() => {})
    return () => { active = false }
  }, [post.data?.id, user?.id])
  useEffect(() => {
    let active = true
    setFriendNotice('')
    if (!user?.id || !post.data?.author_id || user.id === post.data.author_id) { setFriendStatus('none'); return undefined }
    setFriendStatus('loading')
    loadFriendshipStatus(user.id, post.data.author_id).then(status => { if (active) setFriendStatus(status) }).catch(() => { if (active) { setFriendStatus('none'); setFriendNotice('친구 상태를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.') } })
    return () => { active = false }
  }, [post.data?.author_id, user?.id])
  useEffect(() => () => window.clearTimeout(friendNoticeTimer.current), [])
  const revealScrollbar = () => {
    setIsScrolling(true)
    window.clearTimeout(scrollHideTimer.current)
    scrollHideTimer.current = window.setTimeout(() => setIsScrolling(false), 850)
  }
  const toggleHeat = async () => {
    const sessionUser = user || (await supabase?.auth.getSession())?.data?.session?.user
    if (!sessionUser) { onLogin?.(); return }
    const nextHeated = !heated
    try {
      if (post.data?.id) await setPostVote(post.data.id, sessionUser.id, nextHeated)
      setHeated(nextHeated)
      const nextCount = heatCount + (nextHeated ? 1 : -1)
      setHeatCount(nextCount)
      onHeatChange?.(post.data?.id, nextCount)
    } catch { /* Keep the visible count unchanged when persistence fails. */ }
  }
  const toggleBookmark = async () => {
    if (!user) { onLogin?.(); return }
    if (!post.data?.id || bookmarkPending) return
    const nextBookmarked = !bookmarked
    setBookmarkPending(true)
    try {
      await setPostBookmark(post.data.id, user.id, nextBookmarked)
      setBookmarked(nextBookmarked)
    } catch { window.alert('북마크를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.') }
    finally { setBookmarkPending(false) }
  }
  const heatTier = heatTierFor(heatCount)
  const publishedAt = post.data?.published_at || post.data?.created_at
  const publishedLabel = publishedAt ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(publishedAt)) : '날짜 정보 없음'
  const isOwner = Boolean(user?.id && post.data?.author_id === user.id)
  const authorName = String(post.data?.author_display_name || 'FANHEAT').trim().replace(/^@/, '')
  const tags = Array.isArray(post.data?.tags)
    ? post.data.tags.map(tag => String(tag).trim().replace(/^#+/, '')).filter(Boolean)
    : []
  const showFriendNotice = message => {
    setFriendNotice(message)
    window.clearTimeout(friendNoticeTimer.current)
    friendNoticeTimer.current = window.setTimeout(() => setFriendNotice(''), 3200)
  }
  const toggleFriendRequest = async () => {
    if (!user) { onLogin?.(); return }
    if (!post.data?.author_id || friendPending || friendStatus === 'accepted' || friendStatus === 'blocked') return
    setFriendPending(true)
    try {
      if (friendStatus === 'pending') {
        await cancelFriendRequest(user.id, post.data.author_id)
        setFriendStatus('none')
        showFriendNotice(`${authorName}님에게 보낸 친구 요청을 취소했습니다.`)
      } else {
        await sendFriendRequest(user.id, post.data.author_id)
        setFriendStatus('pending')
        showFriendNotice(`${authorName}님에게 친구 요청을 보냈습니다.`)
      }
    } catch {
      showFriendNotice(friendStatus === 'pending' ? '친구 요청을 취소하지 못했습니다. 다시 시도해 주세요.' : '친구 요청을 보내지 못했습니다. 다시 시도해 주세요.')
    } finally { setFriendPending(false) }
  }
  const toggleYoutubeOrientation = () => setYoutubePortrait(current => {
    const next = !current
    if (youtubeOrientationKey) window.localStorage.setItem(youtubeOrientationKey, next ? 'portrait' : 'landscape')
    return next
  })
  return <section ref={detailScrollRoot} className={`post-detail ${isScrolling ? 'is-scrolling' : ''}`} onScroll={revealScrollbar}>
    <header className="detail-mobile-header">
      <button className="detail-list-back" type="button" onClick={onClose} aria-label="게시글 목록으로 돌아가기"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 5-7 7 7 7M7 12h12" /></svg><span>뒤로</span></button>
      <strong title={localizeTitle(post.title) || '게시글 상세'}>{localizeTitle(post.title) || '게시글 상세'}</strong>
      <span className="detail-mobile-header-spacer" aria-hidden="true" />
    </header>
    <div className="detail-hero">
      <div className="detail-meta"><div className="detail-date-actions"><time dateTime={publishedAt || undefined}>{publishedLabel}</time>{isOwner && <button type="button" onClick={() => onEdit(post)}>수정하기</button>}<button className={`detail-bookmark-button ${bookmarked ? 'active' : ''}`} type="button" onClick={toggleBookmark} disabled={bookmarkPending} aria-label={bookmarked ? '북마크 해제' : '북마크 추가'} aria-pressed={bookmarked} title={bookmarked ? '마이페이지 북마크에 저장됨' : '마이페이지 북마크에 저장'}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4.5A1.5 1.5 0 0 1 7.5 3h9A1.5 1.5 0 0 1 18 4.5V21l-6-4-6 4V4.5Z" /></svg></button></div><span className="detail-gift-pending"><img src={`${A}gift_icon.png`} alt="선물" /><b>준비 중</b></span><span className={`detail-heat-count heat-${heatTier}`}><i className="detail-heat-star" aria-hidden="true" /><b>{heatCount.toLocaleString()}건</b></span></div>
      {post.title && <h1>{localizeTitle(post.title)}</h1>}
      {post.data?.summary && <p>{post.data.summary}</p>}
    </div>
    <div className="detail-body">
      {detailSlides.length > 0 && <div className={`detail-carousel ${detailSlides.some(item => item.type !== 'image') ? `detail-mixed-carousel active-${detailSlides[slide]?.type || 'image'}` : ''} ${detailSlides.some(item => item.type === 'youtube') ? 'detail-youtube-carousel' : ''} ${detailSlides[slide]?.type === 'youtube' && youtubePortrait ? 'youtube-portrait' : ''} ${dragging ? 'dragging' : ''}`} onPointerDown={event => { if (detailSlides.length < 2 || event.target.closest('iframe,a,button')) return; dragStart.current = event.clientX; setDragging(true); event.currentTarget.setPointerCapture(event.pointerId) }} onPointerMove={event => { if (dragStart.current !== null) setDragOffset(event.clientX - dragStart.current) }} onPointerUp={finishDetailDrag} onPointerCancel={finishDetailDrag} onClick={event => { if (event.target.closest('button,a,iframe')) return; if (suppressImageClick.current) { suppressImageClick.current = false; return } const activeItem = detailSlides[slide]; if (activeItem?.type === 'image') openDetailImage(activeItem) }}>
        <div className="detail-carousel-viewport"><div className="detail-carousel-track" style={{ transform: `translate3d(calc(-${slide * 100}% + ${dragOffset}px),0,0)` }}>{detailSlides.map((item, index) => <div className={`detail-carousel-slide slide-${item.type}`} key={`${item.type}-${item.src || item.id || item.url || index}`} role={item.type === 'image' ? 'button' : undefined} tabIndex={item.type === 'image' && index === slide ? 0 : undefined} aria-label={item.type === 'image' ? `${Number(item.imageIndex ?? index) + 1}번째 이미지 크게 보기` : undefined} onKeyDown={item.type === 'image' && index === slide ? event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openDetailImage(item) } } : undefined}><MediaContent item={item} title={post.title} index={index} youtubePortrait={item.type === 'youtube' && youtubePortrait} onYoutubeOrientationToggle={toggleYoutubeOrientation} /></div>)}</div></div>
        {detailSlides.length > 1 && <><button className="carousel-prev" onClick={() => setSlide((slide - 1 + detailSlides.length) % detailSlides.length)} aria-label="이전 미디어">‹</button>
        <button className="carousel-next" onClick={() => setSlide((slide + 1) % detailSlides.length)} aria-label="다음 미디어">›</button>
        <div className="detail-carousel-dots">{detailSlides.map((item, index) => <button key={`${item.type}-${item.src || item.id || item.url || index}`} className={slide === index ? 'active' : ''} onClick={() => setSlide(index)} aria-label={`${index + 1}번째 ${mediaTypeLabel(item.type)}`} />)}</div></>}
      </div>}
      {activeImageSource && (activeImageSource.sourceLabel || safeExternalUrl(activeImageSource.sourceUrl)) && <ImageSourceCredit source={activeImageSource} />}
      {lightboxIndex !== null && <ImageLightbox images={detailImageSlides} initialIndex={lightboxIndex} title={localizeTitle(post.title)} onClose={() => setLightboxIndex(null)} />}
      <div className="detail-copy post-rich-content" dangerouslySetInnerHTML={{ __html: richHtmlWithImageCredits(post.data?.body_html || '<p>오랜만에 글올쓰네요. 팬들과 함께 나누고 싶은 순간입니다.</p>', inlineImageSources) }} />
      {tags.length > 0 && <div className="detail-tags detail-body-tags" aria-label="게시글 태그">{tags.map(tag => <span className="detail-tag" key={tag}>#{String(tag).replace(/^#+/, '')}</span>)}</div>}
      <PostSourceCredits sources={articleOnlySources} sourceType={(detailImageSlides.length > 0 || hasInlineImage) ? 'image' : 'article'} />
      <div className="detail-credits">
        <div className="author"><span>작성자</span><button className="author-profile-link" type="button" onClick={() => onOpenAuthor?.({ userId: post.data?.author_id, id: `@${authorName}`, displayName: authorName, image: 'mypage.jpg', artist: 'FANHEAT' })}>@{authorName}</button>{!isOwner && post.data?.author_id && <button className={`friend-action ${friendStatus}`} type="button" onClick={toggleFriendRequest} disabled={friendPending || ['loading', 'accepted', 'blocked'].includes(friendStatus)} aria-label={friendStatus === 'pending' ? `${authorName}님에게 보낸 친구 요청 취소` : friendStatus === 'accepted' ? `${authorName}님과 친구` : `${authorName}님에게 친구 요청 보내기`}>{friendPending ? (friendStatus === 'pending' ? '취소 중…' : '요청 중…') : friendStatus === 'pending' ? '요청 취소' : friendStatus === 'accepted' ? '✓ 친구' : friendStatus === 'blocked' ? '추가 불가' : friendStatus === 'loading' ? '확인 중…' : '친구 추가'}</button>}</div>
        {friendNotice && <p className="friend-action-notice" role="status" aria-live="polite">{friendNotice}</p>}
      </div>
      <div className="reaction-buttons">
        <button className="reaction-gift" type="button" disabled title="기프트 기능은 준비 중입니다"><img src={`${A}gift_icon2.png`} alt="" /><span>GIFT</span><b>준비 중입니다</b></button>
        <button className={`reaction-heat heat-${heatTier} ${heated ? 'is-heated' : ''}`} type="button" onClick={toggleHeat} aria-pressed={heated}><i className="reaction-heat-star" aria-hidden="true" /><span>HEAT</span><b>{heatCount.toLocaleString()}건</b></button>
      </div>
      {/* 포스트 상세 음원 플레이어는 추후 기능 재검토를 위해 렌더링만 임시 중단합니다.
      <DetailAudioPlayer post={post} />
      */}
      <Comments postId={post.data?.id} user={user} onLogin={onLogin} editCommentId={post.editCommentId} onOpenAuthor={onOpenAuthor} />
      <nav className="detail-post-navigation" aria-label="게시글 이동">
        <button type="button" onClick={() => previousPost && onNavigate(previousPost)} disabled={!previousPost}><span aria-hidden="true">←</span><span><small>이전 글</small><strong>{previousPost?.title || '이전 글이 없습니다'}</strong></span></button>
        <button type="button" onClick={() => nextPost && onNavigate(nextPost)} disabled={!nextPost}><span><small>다음 글</small><strong>{nextPost?.title || '다음 글이 없습니다'}</strong></span><span aria-hidden="true">→</span></button>
      </nav>
    </div>
  </section>
}

const initialDraft = {
  title: '',
  summary: '',
  content: '',
  tags: '',
  reference: '',
  referenceLabel: '',
  sourceLinks: [],
  imageSources: [],
  inlineImageSources: [],
  mediaType: 'image',
  mediaUrl: '',
  mediaItems: [],
}

const draftImageSrc = image => image.startsWith('blob:') || /^https?:\/\//.test(image) ? image : `${A}${image}`

const richTextImageUrls = html => {
  if (typeof document === 'undefined') return []
  const template = document.createElement('template')
  template.innerHTML = html || ''
  return [...template.content.querySelectorAll('img[src]')].map(image => image.getAttribute('src')).filter(Boolean).slice(0, 5)
}

const attributionLabel = (label, url, fallback = '출처') => {
  if (String(label || '').trim()) return String(label).trim()
  try { return new URL(url).hostname.replace(/^www\./, '') || fallback } catch { return fallback }
}

function mediaEmbedUrl(type, rawUrl) {
  const url = rawUrl.trim()
  if (type === 'x') { const id = url.match(/(?:x|twitter)\.com\/[^/]+\/status\/(\d+)/i)?.[1]; return id ? `https://platform.twitter.com/embed/Tweet.html?id=${id}&theme=light&dnt=true&lang=ko` : '' }
  if (type === 'youtube') return youtubeEmbedUrl(url)
  if (type === 'instagram' && /instagram\.com\/(p|reel)\//.test(url)) return `${url.split('?')[0].replace(/\/$/, '')}/embed`
  if (type === 'tiktok') { const id = url.match(/\/video\/(\d+)/)?.[1]; return id ? `https://www.tiktok.com/player/v1/${id}` : '' }
  if (type === 'facebook' && /facebook\.com|fb\.watch/.test(url)) return `https://www.facebook.com/plugins/post.php?href=${encodeURIComponent(url)}&show_text=true&width=500`
  return ''
}

const socialMediaType = url => /(?:x|twitter)\.com\/[^/]+\/status\/\d+/i.test(url) ? 'x' : youtubeEmbedUrl(url) ? 'youtube' : /instagram\.com\/(p|reel)\//.test(url) ? 'instagram' : /tiktok\.com/.test(url) ? 'tiktok' : /facebook\.com|fb\.watch/.test(url) ? 'facebook' : ''

const mediaPlatformName = type => ({ image: '이미지', x: 'X', facebook: 'Facebook', instagram: 'Instagram', tiktok: 'TikTok', youtube: 'YouTube' }[type] || '소셜')

function ComposerMediaFrame({ images, mediaItems = [] }) {
  const [slide, setSlide] = useState(0)
  const items = [...images.map((src, index) => ({ type: 'image', src, key: `image-${index}-${src}` })), ...mediaItems.map((item, index) => ({ ...item, src: mediaEmbedUrl(item.type, item.url), key: `${item.type}-${index}-${item.url}` }))].slice(0, MAX_FEATURED_MEDIA_COUNT)
  const active = items[Math.min(slide, Math.max(0, items.length - 1))]
  const platform = active ? mediaPlatformName(active.type) : ''
  useEffect(() => { if (slide >= items.length) setSlide(Math.max(0, items.length - 1)) }, [items.length, slide])
  return <div className={`composer-media-frame ${platform ? 'has-media' : 'is-empty'} ${active?.type ? `media-${active.type}` : ''}`} aria-label="대표 미디어 미리보기 영역">
    {active?.type === 'image' ? <img src={draftImageSrc(active.src)} alt="게시글 대표 미디어 미리보기" /> : active?.src ? <iframe className={`composer-social-embed embed-${active.type}`} src={active.src} title={`${platform} 대표 미디어 미리보기`} allow="autoplay; encrypted-media; picture-in-picture" allowFullScreen /> : <div className="composer-media-empty">
      <strong>대표 미디어 미리보기</strong>
      <p>오른쪽 편집 영역에서 추가한 이미지 또는 X, Facebook, Instagram, TikTok, YouTube 게시물이 여기에 표시됩니다.</p>
    </div>}
    {platform && <b className={`composer-platform-badge platform-${platform.toLowerCase()}`}>{platform}</b>}
    {items.length > 1 && <><button className="composer-media-prev" type="button" onClick={() => setSlide((slide - 1 + items.length) % items.length)} aria-label="이전 대표 미디어">‹</button><button className="composer-media-next" type="button" onClick={() => setSlide((slide + 1) % items.length)} aria-label="다음 대표 미디어">›</button><div className="composer-media-dots">{items.map((item, index) => <button type="button" key={item.key} className={index === slide ? 'active' : ''} onClick={() => setSlide(index)} aria-label={`${index + 1}번째 대표 미디어`} />)}</div><small className="composer-media-count">{slide + 1} / {items.length}</small></>}
  </div>
}

const sourceRowUrl = source => typeof source === 'string' ? source : source?.url || source?.source_url || ''

function ImageSourceCredit({ source }) {
  const url = safeExternalUrl(source?.sourceUrl || source?.source_url || source?.url)
  const label = attributionLabel(source?.sourceLabel || source?.source_label || source?.label, url, '원본 이미지')
  if (!url && !label) return null
  return <div className="featured-image-source-credit" aria-label="사진 출처">
    <span>사진 출처</span>
    {url ? <a href={url} target="_blank" rel="noopener noreferrer">{label}<i aria-hidden="true">↗</i></a> : <strong>{label}</strong>}
  </div>
}

function PostSourceCredits({ sources = [], sourceLabel, sourceUrl, sourceType = 'article' }) {
  const normalizedSources = (sources.length ? sources : [{ label: sourceLabel, url: sourceUrl }]).map((source, index) => ({
    label: String(source?.label || source?.source_label || '').trim(),
    url: safeExternalUrl(sourceRowUrl(source)),
    key: `${index}-${sourceRowUrl(source)}`,
  })).filter(source => source.url)
  if (normalizedSources.length === 0) return null
  const isImageSource = sourceType === 'image'
  return <aside className="post-source-credits" aria-label={isImageSource ? '사진 출처' : '글 출처'}>
    <strong>{isImageSource ? '사진 출처' : '출처'}</strong>
    <span className="post-source-credit-links">{normalizedSources.map((source, index) => <span className="post-source-credit-link" key={source.key}>{index > 0 && <span className="post-source-credit-separator" aria-hidden="true">·</span>}<a href={source.url} target="_blank" rel="noopener noreferrer">{attributionLabel(source.label, source.url, isImageSource ? '사진 원본' : '원문 출처')}<i aria-hidden="true">↗</i></a></span>)}</span>
  </aside>
}

function ComposerPreview({ draft, images }) {
  const tags = draft.tags.split(',').map(tag => tag.trim()).filter(Boolean)
  const sourceLinks = (draft.sourceLinks || []).filter(source => safeExternalUrl(sourceRowUrl(source)))
  return <section className="post-detail compose-preview">
    <div className="detail-hero">
      <div className="detail-meta"><time>2018-07-25 13:23:24</time></div>
      {draft.title && <h1>{draft.title}</h1>}
      {draft.summary && <p>{draft.summary}</p>}
    </div>
    <div className="detail-body">
      <ComposerMediaFrame images={images} mediaItems={draft.mediaItems} />
      {images[0] && (draft.imageSources?.[0]?.label || safeExternalUrl(draft.imageSources?.[0]?.url)) && <ImageSourceCredit source={{ sourceLabel: draft.imageSources[0].label, sourceUrl: draft.imageSources[0].url }} />}
      <div className="detail-copy preview-rich-text post-rich-content" dangerouslySetInnerHTML={{ __html: richHtmlWithImageCredits(draft.content || '<p>본문 내용을 입력하세요.</p>', draft.inlineImageSources || []) }} />
      <PostSourceCredits sources={sourceLinks} sourceLabel={draft.referenceLabel} sourceUrl={draft.reference} />
      <div className="detail-credits"><div className="detail-tags" aria-label="게시글 태그">{tags.map(tag => <span className="detail-tag" key={tag}>#{String(tag).replace(/^#+/, '')}</span>)}</div><div className="author"><span>작성자 :</span><strong>@devdevil0625</strong><em>Preview</em></div></div>
      <div className="reaction-buttons"><button className="reaction-gift" type="button" disabled title="기프트 기능은 준비 중입니다"><img src={`${A}gift_icon2.png`} alt="" /><span>GIFT</span><b>준비 중입니다</b></button><button className="reaction-heat heat-soft" type="button"><i className="reaction-heat-star" aria-hidden="true" /><span>HEAT</span><b>0건</b></button></div>
    </div>
  </section>
}

function RichTextEditor({ value, onChange, onAddImages, remainingImages }) {
  const inlineImageInput = useRef(null)
  const editor = useEditor({
    extensions: [StarterKit, Image.configure({ allowBase64: false }), Youtube.configure({ controls: true, nocookie: true, modestBranding: true })],
    content: value.includes('<') ? value : `<p>${value}</p>`,
    onUpdate: ({ editor: current }) => onChange(current.getHTML()),
  })
  if (!editor) return null
  const run = command => { command(); editor.commands.focus() }
  const addInlineImages = event => {
    const files = [...event.target.files].slice(0, remainingImages)
    const previews = files.map(file => URL.createObjectURL(file))
    previews.forEach((src, index) => editor.chain().focus().setImage({ src, alt: files[index].name }).createParagraphNear().run())
    if (files.length) onAddImages(files, previews)
    event.target.value = ''
  }
  const addYoutube = () => {
    const url = window.prompt('삽입할 YouTube 주소를 입력해 주세요.')?.trim()
    if (!url) return
    if (!youtubeEmbedUrl(url)) { window.alert('올바른 YouTube 또는 youtu.be 주소를 입력해 주세요.'); return }
    editor.commands.setYoutubeVideo({ src: url, width: 640, height: 360 })
    editor.commands.createParagraphNear()
  }
  return <div className={`rich-editor tiptap-editor ${editor.isEmpty ? 'is-empty' : ''}`}>
    <div className="editor-toolbar">
      <select aria-label="문단 종류" value={editor.isActive('heading', { level: 2 }) ? 'h2' : editor.isActive('heading', { level: 3 }) ? 'h3' : 'p'} onChange={event => run(() => event.target.value === 'p' ? editor.chain().focus().setParagraph().run() : editor.chain().focus().toggleHeading({ level: Number(event.target.value.slice(1)) }).run())}><option value="p">본문</option><option value="h2">제목 2</option><option value="h3">제목 3</option></select>
      <button type="button" className={editor.isActive('bold') ? 'active' : ''} onClick={() => editor.chain().focus().toggleBold().run()} aria-label="굵게"><b>B</b></button>
      <button type="button" className={editor.isActive('italic') ? 'active' : ''} onClick={() => editor.chain().focus().toggleItalic().run()} aria-label="기울임"><i>I</i></button>
      <button type="button" className={editor.isActive('underline') ? 'active' : ''} onClick={() => editor.chain().focus().toggleUnderline().run()} aria-label="밑줄"><u>U</u></button>
      <button type="button" className={editor.isActive('strike') ? 'active' : ''} onClick={() => editor.chain().focus().toggleStrike().run()} aria-label="취소선"><s>S</s></button>
      <button type="button" className={editor.isActive('bulletList') ? 'active' : ''} onClick={() => editor.chain().focus().toggleBulletList().run()} aria-label="글머리 목록">•≡</button>
      <button type="button" className={editor.isActive('orderedList') ? 'active' : ''} onClick={() => editor.chain().focus().toggleOrderedList().run()} aria-label="번호 목록">1.</button>
      <button type="button" className={editor.isActive('blockquote') ? 'active' : ''} onClick={() => editor.chain().focus().toggleBlockquote().run()} aria-label="인용문">❝</button>
      <span className="editor-toolbar-separator" />
      <button type="button" className="editor-media-button" onClick={() => inlineImageInput.current?.click()} disabled={remainingImages < 1} aria-label="현재 위치에 이미지 삽입"><span className="editor-button-icon" aria-hidden="true">▧</span><span>이미지</span></button>
      <button type="button" className="editor-media-button" onClick={addYoutube} aria-label="현재 위치에 YouTube 삽입"><span className="editor-button-icon editor-youtube-icon" aria-hidden="true">▶</span><span>YouTube</span></button>
      <input ref={inlineImageInput} hidden type="file" accept="image/jpeg,image/png,image/webp,image/gif" multiple onChange={addInlineImages} />
      <button type="button" onClick={() => editor.chain().focus().undo().run()} disabled={!editor.can().chain().focus().undo().run()} aria-label="실행 취소">↶</button>
      <button type="button" onClick={() => editor.chain().focus().redo().run()} disabled={!editor.can().chain().focus().redo().run()} aria-label="다시 실행">↷</button>
    </div>
    <EditorContent editor={editor} />
    <small>{editor.getText().length}/1000</small>
  </div>
}

function MediaTypeIcon({ type }) {
  if (type === 'image') return <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="4" width="17" height="16" rx="2.5" /><circle cx="9" cy="9" r="1.7" /><path d="m5.5 17 4.2-4.3 3.1 3 2.1-2.1 3.6 3.4" /></svg>
  if (type === 'x') return <svg viewBox="0 0 24 24" aria-hidden="true"><path className="filled" d="M5.2 4h4.1l3.5 4.7L16.9 4h1.9l-5.1 6.1L19.4 20h-4.1l-3.9-5.3L6.8 20H4.9l5.6-6.7L5.2 4Zm3.1 1.5 7.8 13h1.2l-7.8-13H8.3Z" /></svg>
  if (type === 'facebook') return <svg viewBox="0 0 24 24" aria-hidden="true"><path className="filled" d="M13.7 21v-8h2.7l.4-3.1h-3.1v-2c0-.9.3-1.5 1.6-1.5H17V3.6c-.3 0-1.3-.1-2.5-.1-2.5 0-4.2 1.5-4.2 4.3v2.1H7.5V13h2.8v8h3.4Z" /></svg>
  if (type === 'instagram') return <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="3.5" width="17" height="17" rx="5" /><circle cx="12" cy="12" r="4" /><circle className="filled" cx="17.6" cy="6.7" r="1" /></svg>
  if (type === 'tiktok') return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14.2 4v10.7a4.1 4.1 0 1 1-3.4-4" /><path d="M14.2 4c.7 2.8 2.3 4.2 5 4.5" /></svg>
  return <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="6" width="18" height="12" rx="4" /><path className="filled" d="m10.3 9.2 5.3 2.8-5.3 2.8V9.2Z" /></svg>
}

function TagEditor({ value, onChange }) {
  const [adding, setAdding] = useState(false)
  const [input, setInput] = useState('')
  const inputRef = useRef(null)
  const tags = String(value || '').split(',').map(tag => tag.trim().replace(/^#+/, '')).filter(Boolean)
  useEffect(() => { if (adding) inputRef.current?.focus() }, [adding])
  const saveTags = nextTags => onChange(nextTags.join(', '))
  const commit = () => {
    const tag = input.trim().replace(/^#+/, '').replace(/,/g, '')
    if (tag && !tags.some(item => item.toLowerCase() === tag.toLowerCase()) && tags.length < 10) saveTags([...tags, tag])
    setInput('')
    setAdding(false)
  }
  const remove = targetIndex => saveTags(tags.filter((_, index) => index !== targetIndex))
  return <div className="tag-editor">
    <div className="tag-chip-list">
      {tags.map((tag, index) => <span className="tag-chip" key={`${tag}-${index}`}><b>#{tag}</b><button type="button" onClick={() => remove(index)} aria-label={`${tag} 태그 삭제`}>×</button></span>)}
      {adding ? <span className="tag-input-wrap"><span aria-hidden="true">#</span><input ref={inputRef} value={input} maxLength="30" placeholder="태그 입력" onChange={event => setInput(event.target.value)} onBlur={commit} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); commit() } if (event.key === 'Escape') { setInput(''); setAdding(false) } }} /></span> : tags.length < 10 && <button className="tag-add-button" type="button" onClick={() => setAdding(true)}><span>＋</span> 태그 추가</button>}
    </div>
    <small>Enter로 추가 · {tags.length}/10</small>
  </div>
}

function WriteEditor({ draft, setDraft, images, setImages, imageFiles, setImageFiles, inlineImages, setInlineImages, inlineImageFiles, setInlineImageFiles, onClose, onPublish, editing = false }) {
  const { locale, t } = useI18n()
  const exitWriterLabel = { ko: '나가기', en: 'Exit', ja: '終了' }[locale] || '나가기'
  const completeWriterLabel = { ko: '완료', en: 'Done', ja: '完了' }[locale] || '완료'
  const bodyText = String(draft.content || '').replace(/<[^>]*>/g, '').replace(/&nbsp;/gi, ' ').trim()
  const hasBodyContent = Boolean(bodyText || /<(img|iframe)\b/i.test(String(draft.content || '')))
  const canComplete = Boolean(String(draft.title || '').trim() && String(draft.summary || '').trim() && hasBodyContent && String(draft.tags || '').trim())
  const mediaFileInput = useRef(null)
  const update = (key, value) => setDraft(current => ({ ...current, [key]: value }))
  const addInlineImages = files => {
    setInlineImageFiles(current => [...current, ...files])
  }
  const updateContent = value => {
    const nextImages = richTextImageUrls(value)
    setInlineImages(nextImages)
    setDraft(current => ({
      ...current,
      content: value,
      inlineImageSources: nextImages.map(imageUrl => (current.inlineImageSources || []).find(source => source.imageUrl === imageUrl) || { imageUrl, label: '', url: '' }),
    }))
  }
  const selectMediaType = type => {
    update('mediaType', type)
    if (type === 'image') mediaFileInput.current?.click()
  }
  const addRepresentativeImages = event => {
    const selectedFiles = [...event.target.files]
    const available = Math.max(0, MAX_FEATURED_MEDIA_COUNT - images.length - (draft.mediaItems?.length || 0))
    const files = selectedFiles.slice(0, available)
    if (selectedFiles.length > available) window.alert(`대표 미디어는 최대 ${MAX_FEATURED_MEDIA_COUNT}개까지 추가할 수 있습니다.`)
    const previews = files.map(file => URL.createObjectURL(file))
    setImages(current => [...current, ...previews])
    setImageFiles(current => [...current, ...files])
    setDraft(current => ({ ...current, mediaType: 'image', imageSources: [...(current.imageSources || []), ...previews.map(() => ({ label: '', url: '', enabled: false }))] }))
    event.target.value = ''
  }
  const addSocialMedia = () => {
    const url = draft.mediaUrl.trim()
    if (!url || !mediaEmbedUrl(draft.mediaType, url)) { window.alert('퍼가기 가능한 올바른 공개 게시물 주소를 입력해 주세요.'); return }
    if (images.length + (draft.mediaItems?.length || 0) >= MAX_FEATURED_MEDIA_COUNT) { window.alert(`대표 미디어는 최대 ${MAX_FEATURED_MEDIA_COUNT}개까지 추가할 수 있습니다.`); return }
    setDraft(current => ({ ...current, mediaUrl: '', mediaItems: [...(current.mediaItems || []), { type: current.mediaType, url }] }))
  }
  const removeImage = index => {
    const target = images[index]
    if (target?.startsWith('blob:')) URL.revokeObjectURL(target)
    const fileIndex = images.slice(0, index + 1).filter(image => image.startsWith('blob:')).length - 1
    setImages(current => current.filter((_, itemIndex) => itemIndex !== index))
    if (target?.startsWith('blob:')) setImageFiles(current => current.filter((_, itemIndex) => itemIndex !== fileIndex))
    setDraft(current => ({ ...current, imageSources: (current.imageSources || []).filter((_, itemIndex) => itemIndex !== index) }))
  }
  const removeSocialMedia = index => setDraft(current => ({ ...current, mediaItems: (current.mediaItems || []).filter((_, itemIndex) => itemIndex !== index) }))
  const removeRepresentativeMedia = () => {
    images.filter(image => image.startsWith('blob:')).forEach(URL.revokeObjectURL)
    setImages([]); setImageFiles([]); setDraft(current => ({ ...current, mediaUrl: '', mediaItems: [], imageSources: [] }))
  }
  const updateImageSource = (index, changes) => setDraft(current => {
    const next = images.map((_, itemIndex) => ({ label: '', url: '', ...(current.imageSources?.[itemIndex] || {}) }))
    next[index] = { ...next[index], ...changes }
    return { ...current, imageSources: next }
  })
  const removeImageSource = index => updateImageSource(index, { label: '', url: '', enabled: false })
  const displayedSourceLinks = draft.sourceLinks?.length ? draft.sourceLinks : ['']
  const updateSourceLink = (index, value) => setDraft(current => {
    const next = current.sourceLinks?.length ? [...current.sourceLinks] : ['']
    next[index] = typeof next[index] === 'object' ? { ...next[index], url: value } : value
    return { ...current, sourceLinks: next }
  })
  const addSourceLink = () => setDraft(current => ({ ...current, sourceLinks: [...(current.sourceLinks || []), ''].slice(0, 10) }))
  const removeSourceLink = index => setDraft(current => ({ ...current, sourceLinks: (current.sourceLinks || []).filter((_, itemIndex) => itemIndex !== index) }))
  const music = [['music1.jpg', '비도 오고 그래서', '헤이즈 (Heize)'], ['music2.jpg', 'Siren', '선미'], ['music3.jpg', '몰랐니', "소녀시대-Oh!GG"]]
  return <section className="write-editor" aria-label="게시글 작성">
    <div className="write-editor-head"><div><h2>{t('newPost')}</h2><p>팬들과 나누고 싶은 순간을 자유롭게 기록해 보세요.</p></div><div className="write-editor-actions"><button type="button" onClick={onClose} aria-label={exitWriterLabel}><span aria-hidden="true">←</span>{exitWriterLabel}</button><button className="write-editor-complete" type="button" onClick={onPublish} disabled={!canComplete}>{editing ? '수정 완료' : completeWriterLabel}</button></div></div>
    <label className="write-field write-title-field required"><span>{t('title')}</span><input value={draft.title} placeholder="제목을 입력하세요" onChange={e => update('title', e.target.value)} /></label>
    <label className="write-field write-summary-field required"><span>{t('summary')}</span><div><input value={draft.summary} placeholder="게시글을 소개하는 한 줄 내용을 입력하세요" maxLength="60" onChange={e => update('summary', e.target.value)} /><small>{draft.summary.length}/60</small></div></label>
    <div className="write-field representative-media-field"><span>대표 미디어</span><div className="representative-media-editor"><p>대표 이미지와 소셜 게시물을 합쳐 최대 {MAX_FEATURED_MEDIA_COUNT}개까지 추가할 수 있습니다. 본문 에디터의 이미지는 이 제한에 포함되지 않습니다. <b>{images.length + (draft.mediaItems?.length || 0)} / {MAX_FEATURED_MEDIA_COUNT}</b></p><div className="media-type-options">{[['image','이미지'],['x','X'],['facebook','Facebook'],['instagram','Instagram'],['tiktok','TikTok'],['youtube','YouTube']].map(([type, label]) => <button type="button" key={type} className={draft.mediaType === type ? 'active' : ''} onClick={() => selectMediaType(type)} disabled={images.length + (draft.mediaItems?.length || 0) >= MAX_FEATURED_MEDIA_COUNT}><i><MediaTypeIcon type={type} /></i>{label}</button>)}</div><input ref={mediaFileInput} hidden type="file" accept="image/jpeg,image/png,image/webp,image/gif" multiple onChange={addRepresentativeImages} />{draft.mediaType !== 'image' && <label className="social-media-url"><span>{mediaPlatformName(draft.mediaType)} 공개 게시물 URL</span><div><input value={draft.mediaUrl} placeholder={draft.mediaType === 'x' ? 'https://x.com/account/status/...' : 'https://'} onChange={event => update('mediaUrl', event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); addSocialMedia() } }} /><button type="button" onClick={addSocialMedia}>추가</button></div></label>}<div className="representative-media-thumbs">{images.map((image, index) => <article key={image}><img src={draftImageSrc(image)} alt={`대표 이미지 ${index + 1}`} /><span>이미지</span><button type="button" onClick={() => removeImage(index)} aria-label={`${index + 1}번째 이미지 삭제`}>×</button></article>)}{(draft.mediaItems || []).map((item, index) => <article className={`media-thumb-${item.type}`} key={`${item.type}-${item.url}-${index}`}>{item.type === 'youtube' ? <img src={youtubeThumbnailUrl(item.url)} alt="YouTube 영상 썸네일" onError={event => { const fallback = youtubeThumbnailUrl(item.url, 'mqdefault'); if (event.currentTarget.src !== fallback) event.currentTarget.src = fallback }} /> : <i><MediaTypeIcon type={item.type} /></i>}<span>{mediaPlatformName(item.type)}</span><button type="button" onClick={() => removeSocialMedia(index)} aria-label={`${mediaPlatformName(item.type)} 미디어 삭제`}>×</button></article>)}</div>{images.length > 0 && <div className="representative-image-sources"><p>이미지 출처 <small>선택</small></p>{images.map((image, index) => { const source = draft.imageSources?.[index] || {}; const sourceOpen = Boolean(source.enabled || source.url || source.label); return <section className="representative-image-source" key={`${image}-source`}><img src={draftImageSrc(image)} alt="" /><strong>{index + 1}번 이미지</strong>{sourceOpen ? <><label><span>출처 URL</span><input type="url" value={source.url || ''} onChange={event => updateImageSource(index, { url: event.target.value, enabled: true })} placeholder="https:// 원본 페이지 주소" aria-label={`${index + 1}번째 이미지 출처 URL`} /></label><button className="image-source-remove" type="button" onClick={() => removeImageSource(index)}>출처 제거</button></> : <button className="image-source-add" type="button" onClick={() => updateImageSource(index, { enabled: true })}>+ 출처 등록</button>}</section>})}</div>}{(images.length > 0 || (draft.mediaItems?.length || 0) > 0) && <button className="clear-representative-media" type="button" onClick={removeRepresentativeMedia}>대표 미디어 전체 비우기</button>}</div></div>
    <div className="write-field required editor-content-field"><span>{t('content')}</span><div><p className="editor-media-guide">여기는 게시글 <b>본문</b>입니다. 위의 대표 미디어와 별개로 글과 본문 이미지를 편집할 수 있습니다.</p><RichTextEditor value={draft.content} onChange={updateContent} onAddImages={addInlineImages} remainingImages={Math.max(0, 5 - inlineImages.length)} /></div></div>
    <div className="write-field required tag-write-field"><span>{t('tags')}</span><TagEditor value={draft.tags} onChange={value => update('tags', value)} /></div>
    <div className="write-field post-source-field"><span>글 출처 <small>선택</small></span><div className="post-source-inputs"><div className="post-source-rows">{displayedSourceLinks.map((source, index) => <div className="post-source-row" key={index}><input type="url" value={sourceRowUrl(source)} onChange={event => updateSourceLink(index, event.target.value)} placeholder="https:// 원문 주소" aria-label={`글 출처 URL ${index + 1}`} />{(displayedSourceLinks.length > 1 || sourceRowUrl(source)) && <button type="button" onClick={() => removeSourceLink(index)} aria-label={`${index + 1}번째 글 출처 삭제`}>×</button>}</div>)}</div><button className="post-source-add" type="button" onClick={addSourceLink} disabled={displayedSourceLinks.length >= 10}>+ 출처 URL 추가</button><small>출처 URL은 최대 10개까지 추가할 수 있으며 게시글 상세에서 원문 링크로 표시됩니다.</small></div></div>
    {/* 음원 첨부 기능은 보존하되 현재 서비스 화면에서는 노출하지 않는다. */}
    {POST_MUSIC_ATTACHMENT_ENABLED && <div className="write-field"><span>{t('addMusic')}</span><div><button className="music-search" type="button">▷ {t('musicSearch')}</button><div className="selected-music">{music.map(([image,title,artist], index) => <article key={title}><b>{String(index + 1).padStart(2,'0')}</b><img src={`${A}${image}`} alt="" /><span><strong>{title}</strong><small>{artist}</small></span><button type="button">×</button></article>)}</div></div></div>}
    <p className="write-guide"><b>※ 글 작성 이용안내</b><br />타인의 권리를 침해하지 않는 콘텐츠를 작성해 주세요. 본문 툴바에서 이미지는 최대 5장, YouTube 영상은 필요한 위치에 추가할 수 있습니다.</p>
    <button className="publish-button" type="button" onClick={onPublish}>{editing ? '수정 완료' : t('publish')}</button>
  </section>
}

function AuthModal({ onClose }) {
  const { locale, setLocale, t } = useI18n()
  const googlePreparingLabel = { ko: 'Google 로그인 준비 중', en: 'Google login coming soon', ja: 'Googleログイン準備中' }[locale] || 'Google 로그인 준비 중'
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState('')
  useEffect(() => {
    const closeOnEscape = event => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onClose])
  const submit = async event => {
    event.preventDefault()
    if (!email.trim() || password.length < 6) return
    setPending(true); setMessage('')
    try {
      const result = mode === 'login'
        ? await supabase.auth.signInWithPassword({ email: email.trim(), password })
        : await supabase.auth.signUp({ email: email.trim(), password, options: { emailRedirectTo: window.location.origin } })
      if (result.error) throw result.error
      if (mode === 'signup' && !result.data.session) setMessage('인증 메일을 보냈습니다. 이메일을 확인해 주세요.')
      else onClose()
    } catch (cause) { setMessage(cause.message) }
    finally { setPending(false) }
  }
  const oauth = async provider => {
    setPending(true); setMessage('')
    try {
      if (!supabase) throw new Error('로그인 서비스 설정을 확인해 주세요.')
      const options = {
        redirectTo: `${window.location.origin}/`,
        ...(provider === 'google' ? { scopes: 'openid email profile', queryParams: { prompt: 'select_account' } } : {}),
      }
      const { error } = await supabase.auth.signInWithOAuth({ provider, options })
      if (error) throw error
    } catch (cause) {
      const providerName = provider === 'google' ? 'Google' : '카카오'
      const providerDisabled = /provider.*(disabled|not enabled|not supported)|unsupported provider/i.test(cause?.message || '')
      setMessage(providerDisabled ? `${providerName} 로그인이 아직 서버에서 활성화되지 않았습니다. 잠시 후 다시 시도해 주세요.` : cause?.message || `${providerName} 로그인을 시작하지 못했습니다.`)
      setPending(false)
    }
  }
  return <div className="auth-overlay" role="presentation" onMouseDown={event => event.target === event.currentTarget && onClose()}>
    <section className="auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-title">
      <button className="auth-close" onClick={onClose} aria-label="로그인 창 닫기">×</button>
      <div className="auth-language" role="group" aria-label={t('language')}>{[['ko','🇰🇷 KO'],['en','🇺🇸 EN'],['ja','🇯🇵 JPN']].map(([code, label]) => <button type="button" className={locale === code ? 'active' : ''} onClick={() => setLocale(code)} aria-pressed={locale === code} key={code}>{label}</button>)}</div>
      <div className="auth-brand"><img src={`${A}fanheat-logo.png`} alt="FAN HEAT" /><span>TURN UP THE HEAT</span></div>
      <div className="auth-content">
        <h2 id="auth-title">{mode === 'login' ? t('authTitle') : t('signupTitle')}</h2>
        <p>{mode === 'login' ? t('authDesc') : t('signupDesc')}</p>
        <form onSubmit={submit}>
          <label><span>{t('email')}</span><input type="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="fan@fanheat.com" required autoFocus /></label>
          <label><span>{t('password')}</span><input type="password" value={password} onChange={event => setPassword(event.target.value)} placeholder={t('passwordHint')} minLength="6" required /></label>
          <button className="email-auth" type="submit" disabled={pending}>{pending ? t('processing') : mode === 'login' ? t('emailLogin') : t('emailSignup')}</button>
        </form>
        {message && <p className="auth-message">{message}</p>}
        <div className="auth-divider"><span>{t('or')}</span></div>
        <button className="social-auth google is-preparing" type="button" disabled aria-label={googlePreparingLabel}><img src={`${A}google-g.svg`} alt="" /> {googlePreparingLabel}</button>
        <button className="social-auth kakao" type="button" onClick={() => oauth('kakao')} disabled={pending}><img src={`${A}kakao-talk.svg`} alt="" /> {t('kakao')}</button>
        <p className="auth-switch">{mode === 'login' ? t('noAccount') : t('haveAccount')} <button onClick={() => setMode(current => current === 'login' ? 'signup' : 'login')}>{mode === 'login' ? t('signup') : t('login')}</button></p>
        <p className="auth-terms">{t('terms')}</p>
      </div>
    </section>
  </div>
}

function Player({ songIndex, onSelectSong, onPlayingChange, onClose, items = [] }) {
  const audio = useRef(null)
  const [playing, setPlaying] = useState(false)
  const [continuous, setContinuous] = useState(false)
  const current = songIndex === null ? null : items[songIndex]
  const audioUrl = current?.[3]?.audio_url || ''
  const findNextPlayable = start => {
    for (let offset = 1; offset <= items.length; offset += 1) {
      const index = (start + offset) % items.length
      if (items[index]?.[3]?.audio_url) return index
    }
    return null
  }
  const playCurrent = async () => {
    if (!audioUrl || !audio.current) return
    try { await audio.current.play(); setPlaying(true) } catch { setPlaying(false) }
  }
  useEffect(() => {
    if (!audio.current) return
    audio.current.pause()
    audio.current.currentTime = 0
    setPlaying(false)
    if (!continuous || songIndex === null) return
    if (audioUrl) playCurrent()
    else { const next = findNextPlayable(songIndex); if (next !== null && next !== songIndex) onSelectSong(next) }
  }, [songIndex, audioUrl])
  useEffect(() => { onPlayingChange?.(playing) }, [playing, onPlayingChange])
  useEffect(() => () => onPlayingChange?.(false), [onPlayingChange])
  if (!current) return null
  const [title, artist, image] = current
  const toggle = async () => {
    if (!audioUrl) return
    if (playing) { audio.current.pause(); setPlaying(false) } else await playCurrent()
  }
  const toggleContinuous = () => {
    const nextValue = !continuous
    setContinuous(nextValue)
    if (!nextValue) return
    if (audioUrl) playCurrent()
    else { const next = findNextPlayable(songIndex); if (next !== null) onSelectSong(next) }
  }
  const handleEnded = () => {
    setPlaying(false)
    if (!continuous) return
    const next = findNextPlayable(songIndex)
    if (next !== null) onSelectSong(next)
  }
  return <div className={`player ${continuous ? 'continuous' : ''}`}><audio ref={audio} src={audioUrl || undefined} onEnded={handleEnded} /><img src={assetSrc(image)} alt={`${title} 커버`} /><div><b>{title}</b><span>{audioUrl ? artist : `${artist} · 음원 없음`}</span></div><button className="player-continuous" type="button" onClick={toggleContinuous} aria-pressed={continuous}><i aria-hidden="true">↻</i><span>{continuous ? '연속 재생 중' : '연속 재생하기'}</span></button><button className="player-toggle" onClick={toggle} disabled={!audioUrl} aria-label={!audioUrl ? '재생 가능한 음원이 없습니다' : playing ? '일시정지' : '재생'}>{playing ? 'Ⅱ' : '▶'}</button><button className="player-close" onClick={onClose} aria-label="플레이어 닫기">×</button></div>
}

function MobileNavIcon({ type }) {
  const paths = {
    home: <><path d="M4 10.5 12 4l8 6.5V20h-5v-6h-6v6H4v-9.5Z" /></>,
    artists: <><circle cx="10" cy="8" r="3" /><path d="M4.5 20c.4-4 2.2-6 5.5-6 2.1 0 3.6.8 4.5 2.4M18 5v8M16 7h4M18 13c0 2-1.2 3.2-3 3.2" /></>,
    vote: <><path d="M5 9h14l1 11H4L5 9Z" /><path d="m8 4 2.3-2 4.3 4.2-2.3 2L8 4ZM8 14l2.2 2.2L15 11.5" /></>,
    write: <><rect x="4" y="4" width="16" height="16" rx="4" /><path d="M12 8v8M8 12h8" /></>,
    my: <><circle cx="12" cy="8" r="3.5" /><path d="M5 20c.5-4.4 2.8-6.5 7-6.5s6.5 2.1 7 6.5" /></>,
  }
  return <svg viewBox="0 0 24 24" aria-hidden="true">{paths[type]}</svg>
}

function MobileAppNav({ active, hidden, onHome, onArtists, onVote, onWrite, onMyPage }) {
  const items = [
    ['home', '홈', onHome],
    ['artists', '아티스트', onArtists],
    ['vote', '투표', onVote],
    ['write', '글쓰기', onWrite],
    ['my', '마이', onMyPage],
  ]
  return <nav className={`mobile-app-nav ${hidden ? 'is-hidden' : ''}`} aria-label="모바일 앱 메뉴">
    {items.map(([key, label, action]) => <button type="button" className={`nav-${key} ${active === key ? 'active' : ''}`} onClick={action} aria-current={active === key ? 'page' : undefined} key={key}><i><MobileNavIcon type={key} /></i><span>{label}</span></button>)}
  </nav>
}

function MobileMyPageTabs({ active, unreadMessageCount = 0, onSelect, onBack }) {
  const [moreOpen, setMoreOpen] = useState(false)
  const items = [
    ['profile', 'MY 홈', <><circle cx="12" cy="8" r="3.5" /><path d="M5 20c.5-4.4 2.8-6.5 7-6.5s6.5 2.1 7 6.5" /></>],
    ['posts', '포스트', <><rect x="5" y="4" width="14" height="16" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></>],
    ['bookmarks', '북마크', <path d="M7 4h10v16l-5-3.5L7 20V4Z" />],
    ['followers', '프렌즈', <><circle cx="9" cy="8" r="3" /><circle cx="17" cy="10" r="2.5" /><path d="M3.5 20c.4-4 2.2-6 5.5-6s5.1 2 5.5 6M14 15.5c3.8-.4 5.8 1.1 6.2 4.5" /></>],
    ['comments', '코멘트', <path d="M5 5h14v10H11l-4 4v-4H5V5Z" />],
    ['messages', '메시지', <><rect x="4" y="6" width="16" height="12" rx="2" /><path d="m5 8 7 5 7-5" /></>],
  ]
  const primaryItems = items.slice(0, 3)
  const moreItems = items.slice(3)
  const moreActive = moreItems.some(([key]) => key === active)
  useEffect(() => {
    if (!moreOpen) return undefined
    const closeOnEscape = event => { if (event.key === 'Escape') setMoreOpen(false) }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [moreOpen])
  const selectItem = key => { setMoreOpen(false); onSelect(key) }
  return <>
    <nav className="mobile-my-page-tabs" aria-label="마이페이지 콘텐츠 메뉴">
      <div className="mobile-my-page-appbar">
        <button className="mobile-my-page-back" type="button" onClick={onBack} aria-label="마이페이지에서 나가기"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 5-7 7 7 7" /></svg></button>
        <strong>마이페이지</strong>
      </div>
      <div className="mobile-my-page-tab-list" role="list">
        {primaryItems.map(([key, label]) => <button type="button" className={active === key ? 'active' : ''} onClick={() => selectItem(key)} aria-current={active === key ? 'page' : undefined} key={key}><span>{label}</span></button>)}
        <button type="button" className={moreActive ? 'active' : ''} onClick={() => setMoreOpen(true)} aria-haspopup="dialog" aria-expanded={moreOpen}><span>더보기</span>{unreadMessageCount > 0 && <b aria-label={`읽지 않은 메시지 ${unreadMessageCount}개`}>{unreadMessageCount > 99 ? '99+' : unreadMessageCount}</b>}</button>
      </div>
    </nav>
    {moreOpen && <div className="mobile-my-page-more-overlay" role="presentation" onMouseDown={event => event.target === event.currentTarget && setMoreOpen(false)}>
      <section className="mobile-my-page-more-sheet" role="dialog" aria-modal="true" aria-labelledby="mobile-my-page-more-title">
        <div className="mobile-my-page-more-handle" aria-hidden="true" />
        <header><div><small>MY PAGE</small><h2 id="mobile-my-page-more-title">더보기</h2></div><button type="button" onClick={() => setMoreOpen(false)} aria-label="더보기 메뉴 닫기">×</button></header>
        <div className="mobile-my-page-more-list">
          {moreItems.map(([key, label, icon]) => <button type="button" className={active === key ? 'active' : ''} onClick={() => selectItem(key)} aria-current={active === key ? 'page' : undefined} key={key}><i><svg viewBox="0 0 24 24" aria-hidden="true">{icon}</svg></i><span>{label}</span>{key === 'messages' && unreadMessageCount > 0 && <b>{unreadMessageCount > 99 ? '99+' : unreadMessageCount}</b>}<em aria-hidden="true">›</em></button>)}
        </div>
      </section>
    </div>}
  </>
}

function FanHeatApp() {
  const [query, setQuery] = useState('')
  const [searchFilters, setSearchFilters] = useState({ from: '', to: '', author: 'all', sort: 'latest' })
  const [menuOpen, setMenuOpen] = useState(false)
  const [songIndex, setSongIndex] = useState(null)
  const [songPlaying, setSongPlaying] = useState(false)
  const [chartCollapsed, setChartCollapsed] = useState(false)
  const [selectedPost, setSelectedPost] = useState(null)
  const [selectedStar, setSelectedStar] = useState(null)
  const [artistDirectory, setArtistDirectory] = useState(false)
  const [myPage, setMyPage] = useState(false)
  const [myPageTab, setMyPageTab] = useState('posts')
  const [myPageMobileSection, setMyPageMobileSection] = useState('profile')
  const [selectedFan, setSelectedFan] = useState(null)
  const [user, setUser] = useState(null)
  const [unreadMessageCount, setUnreadMessageCount] = useState(0)
  const [home, setHome] = useState({ tracks: [], awards: [], posts: [], artists: [], artistRankings: { today: [], week: [], month: [] }, heroSlides: [] })
  const [dataNotice, setDataNotice] = useState('')
  const [authOpen, setAuthOpen] = useState(false)
  const [writing, setWriting] = useState(false)
  const [mobileVoteOpen, setMobileVoteOpen] = useState(false)
  const [mobileNavVisible, setMobileNavVisible] = useState(true)
  const [editingPost, setEditingPost] = useState(null)
  const [draft, setDraft] = useState(initialDraft)
  const [draftImages, setDraftImages] = useState([])
  const [draftImageFiles, setDraftImageFiles] = useState([])
  const [draftInlineImages, setDraftInlineImages] = useState([])
  const [draftInlineImageFiles, setDraftInlineImageFiles] = useState([])
  const composeShortcut = useRef(new URLSearchParams(window.location.search).get('compose') === '1')
  const postPathId = () => window.location.pathname.match(/^\/posts\/([0-9a-f-]+)\/?$/i)?.[1] || null
  const scrollTimers = useRef(new Map())
  const mobileNavLastScrollY = useRef(0)
  const revealTransientScrollbar = event => {
    const target = event.target
    if (!(target instanceof HTMLElement) || target.scrollHeight <= target.clientHeight) return
    if (target.classList.contains('feed')) {
      const viewport = target.clientHeight
      const content = target.scrollHeight
      const thumbHeight = Math.max(46, viewport * viewport / content)
      const progress = target.scrollTop / Math.max(1, content - viewport)
      const thumbTop = target.scrollTop + 4 + progress * Math.max(0, viewport - thumbHeight - 8)
      target.style.setProperty('--feed-scroll-height', `${thumbHeight}px`)
      target.style.setProperty('--feed-scroll-top', `${thumbTop}px`)
    }
    target.classList.add('is-scrolling')
    window.clearTimeout(scrollTimers.current.get(target))
    scrollTimers.current.set(target, window.setTimeout(() => {
      target.classList.remove('is-scrolling')
      scrollTimers.current.delete(target)
    }, 700))
  }
  const openWriter = () => { if (!user) { setAuthOpen(true); return }; setEditingPost(null); setSelectedPost(null); setSelectedStar(null); setSelectedFan(null); setArtistDirectory(false); setMyPage(false); setDraft({ ...initialDraft }); setDraftImages([]); setDraftImageFiles([]); setDraftInlineImages([]); setDraftInlineImageFiles([]); setWriting(true) }
  const openPostEditor = post => {
    const editablePost = Array.isArray(post)
      ? { title: post[0], image: post[1], index: home.posts.indexOf(post), data: post[2] || {} }
      : { ...post, data: post?.data || {} }
    const postData = editablePost.data
    if (!user || postData.author_id !== user.id) return
    const referenceUrl = postData.reference_url || ''
    const mediaType = socialMediaType(referenceUrl)
    const storedMediaItems = Array.isArray(postData.media_items) ? postData.media_items.filter(item => item?.type && item?.url) : []
    const mediaItems = storedMediaItems.length ? storedMediaItems : mediaType ? [{ type: mediaType, url: referenceUrl }] : []
    const storedInlineSources = Array.isArray(postData.inline_image_sources) ? postData.inline_image_sources : []
    const inlineImageUrls = storedInlineSources.map(source => source?.image_url).filter(Boolean)
    const editableInlineImages = inlineImageUrls.length ? inlineImageUrls : richTextImageUrls(postData.body_html || postData.content || '')
    setEditingPost(editablePost)
    setDraft({
      ...initialDraft,
      title: postData.title || editablePost.title || '',
      summary: postData.summary || editablePost.summary || '',
      content: postData.body_html || postData.content || '',
      tags: Array.isArray(postData.tags) ? postData.tags.join(', ') : postData.tags || '',
      reference: postData.source_url || (mediaType ? '' : referenceUrl),
      referenceLabel: postData.source_label || '',
      sourceLinks: Array.isArray(postData.source_links) && postData.source_links.length
        ? postData.source_links
        : postData.source_url ? [{ label: postData.source_label || '', url: postData.source_url }] : [],
      imageSources: Array.isArray(postData.image_sources) ? postData.image_sources : [],
      inlineImageSources: editableInlineImages.map(imageUrl => {
        const source = storedInlineSources.find(item => item?.image_url === imageUrl) || {}
        return { imageUrl, label: source.source_label || '', url: source.source_url || '' }
      }),
      mediaType: mediaItems[0]?.type || mediaType || 'image',
      mediaItems,
    })
    setDraftImages([...(postData.images || editablePost.images || [])])
    setDraftImageFiles([])
    setDraftInlineImages(editableInlineImages)
    setDraftInlineImageFiles([])
    setSelectedPost(null)
    setWriting(true)
  }
  const closeWriter = () => { setWriting(false); if (editingPost) setSelectedPost(editingPost); setEditingPost(null) }
  const goHome = () => { setMobileVoteOpen(false); setWriting(false); setEditingPost(null); setSelectedPost(null); setSelectedStar(null); setSelectedFan(null); setArtistDirectory(false); setMyPage(false); if (window.location.pathname.startsWith('/posts/')) window.history.pushState({}, '', '/') }
  const openMyPage = (section = 'profile') => { if (!user) { setAuthOpen(true); return }; setWriting(false); setSelectedPost(null); setSelectedStar(null); setSelectedFan(null); setMyPageMobileSection(section); setMyPageTab(section === 'profile' ? 'posts' : section); setMyPage(true) }
  const selectMyPageMobileSection = section => {
    setMyPageMobileSection(section)
    if (section !== 'profile') setMyPageTab(section)
    window.requestAnimationFrame(() => {
      const scrollRoot = document.querySelector('.app')
      if (scrollRoot) scrollRoot.scrollTo({ top: 0, behavior: 'smooth' })
      else window.scrollTo({ top: 0, behavior: 'smooth' })
    })
  }
  const openFanPage = profile => {
    if (!user) { setAuthOpen(true); return }
    setWriting(false)
    setSelectedPost(null)
    setSelectedStar(null)
    setArtistDirectory(false)
    setMyPageTab('posts')
    setMyPageMobileSection('profile')
    setSelectedFan(profile)
    setMyPage(true)
  }
  const logout = async () => { await supabase?.auth.signOut(); goHome() }
  useEffect(() => {
    if (!supabase) { setDataNotice('Supabase 환경 변수를 확인해 주세요.'); return undefined }
    supabase.auth.getUser().then(({ data }) => setUser(data.user || null))
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => setUser(session?.user || null))
    loadHomeData().then(setHome).catch(error => setDataNotice(`DB 연결 실패: ${error.message}`))
    return () => listener.subscription.unsubscribe()
  }, [])
  useEffect(() => {
    if (!home.posts.length) return undefined
    const syncPostFromLocation = () => {
      const id = postPathId()
      if (!id) { setSelectedPost(null); return }
      const index = home.posts.findIndex(([, , data]) => data?.id === id)
      if (index < 0) { setSelectedPost(null); window.history.replaceState({}, '', '/'); return }
      setSelectedPost({ title: home.posts[index][0], image: home.posts[index][1], index, data: home.posts[index][2] || {} })
    }
    syncPostFromLocation()
    window.addEventListener('popstate', syncPostFromLocation)
    return () => window.removeEventListener('popstate', syncPostFromLocation)
  }, [home.posts])
  useEffect(() => {
    if (!user?.id) { setUnreadMessageCount(0); return undefined }
    let active = true
    const refreshUnread = () => loadUnreadMessageCount(user.id).then(count => { if (active) setUnreadMessageCount(count) }).catch(() => {})
    refreshUnread()
    const timer = window.setInterval(refreshUnread, 30000)
    window.addEventListener('focus', refreshUnread)
    return () => { active = false; window.clearInterval(timer); window.removeEventListener('focus', refreshUnread) }
  }, [user?.id])
  useEffect(() => () => {
    scrollTimers.current.forEach(timer => window.clearTimeout(timer))
    scrollTimers.current.clear()
  }, [])
  useEffect(() => {
    const mobileQuery = window.matchMedia('(max-width: 700px)')
    let frame = 0
    mobileNavLastScrollY.current = Math.max(0, window.scrollY)
    setMobileNavVisible(true)
    const updateMobileNav = () => {
      frame = 0
      if (!mobileQuery.matches || mobileVoteOpen || menuOpen) return
      const currentY = Math.max(0, window.scrollY)
      const delta = currentY - mobileNavLastScrollY.current
      const pageBottom = document.documentElement.scrollHeight
      const reachedBottom = currentY + window.innerHeight >= pageBottom - 24
      if (currentY <= 24 || reachedBottom) setMobileNavVisible(true)
      else if (delta > 7 && currentY > 88) setMobileNavVisible(false)
      else if (delta < -7) setMobileNavVisible(true)
      if (Math.abs(delta) > 7 || currentY <= 24) mobileNavLastScrollY.current = currentY
    }
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(updateMobileNav)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [writing, myPage, artistDirectory, selectedStar, selectedPost, mobileVoteOpen, menuOpen])
  useEffect(() => {
    if (!mobileVoteOpen) return undefined
    const closeOnEscape = event => event.key === 'Escape' && setMobileVoteOpen(false)
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [mobileVoteOpen])
  useEffect(() => {
    if (!composeShortcut.current) return
    if (!user) { setAuthOpen(true); return }
    composeShortcut.current = false
    setAuthOpen(false)
    openWriter()
    const url = new URL(window.location.href)
    url.searchParams.delete('compose')
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
  }, [user])
  useEffect(() => {
    const origin = window.location.origin
    const baseTitle = 'FANHEAT | 팬심이 연결되는 글로벌 커뮤니티'
    const baseDescription = '사람과 AI의 팬심이 만나는 곳. 전 세계 팬들과 아티스트의 빛나는 순간을 발견하고 함께 이야기하세요.'
    const title = selectedStar ? `${selectedStar.name} 프로필·앨범·갤러리 | FANHEAT` : selectedPost ? `${selectedPost.title} | FANHEAT K-POP 팬 콘텐츠` : artistDirectory ? 'K-POP 아티스트 찾기 | FANHEAT' : baseTitle
    const description = selectedStar ? `${selectedStar.name}의 프로필, 데뷔 정보, 앨범, 대표곡, 활동 갤러리와 팬 커뮤니티를 확인하세요.` : selectedPost ? selectedPost.data?.summary || `${selectedPost.title}에 관한 K-POP 팬 콘텐츠와 이야기를 확인하세요.` : artistDirectory ? '국내외 K-POP 가수와 아이돌 그룹을 검색하고 최신 앨범과 팬 콘텐츠를 만나보세요.' : baseDescription
    const image = new URL(assetSrc(selectedStar?.image || selectedPost?.image || 'auth-concert.jpg'), origin).href
    const canonicalUrl = selectedPost?.data?.id ? `${origin}/posts/${selectedPost.data.id}` : `${origin}${window.location.pathname}`
    const tags = Array.isArray(selectedPost?.data?.tags) ? selectedPost.data.tags.map(tag => String(tag).replace(/^#+/, '').trim()).filter(Boolean) : []
    const setMeta = (selector, attribute, value) => { let node = document.head.querySelector(selector); if (!node) { node = document.createElement('meta'); const match = selector.match(/^meta\[(name|property)="([^"]+)"\]$/); if (!match) return; node.setAttribute(match[1], match[2]); document.head.appendChild(node) } node.setAttribute(attribute, value) }
    document.title = title
    setMeta('meta[name="description"]', 'content', description)
    setMeta('meta[property="og:title"]', 'content', title)
    setMeta('meta[property="og:description"]', 'content', description)
    setMeta('meta[property="og:image"]', 'content', image)
    setMeta('meta[property="og:url"]', 'content', canonicalUrl)
    setMeta('meta[property="og:type"]', 'content', selectedPost ? 'article' : 'website')
    setMeta('meta[name="twitter:title"]', 'content', title)
    setMeta('meta[name="twitter:description"]', 'content', description)
    setMeta('meta[name="twitter:image"]', 'content', image)
    setMeta('meta[name="keywords"]', 'content', [...tags, 'K-POP', '팬 커뮤니티', 'FANHEAT'].join(', '))
    setMeta('meta[name="robots"]', 'content', 'index, follow, max-image-preview:large')
    setMeta('meta[property="article:published_time"]', 'content', selectedPost?.data?.published_at || selectedPost?.data?.created_at || '')
    setMeta('meta[property="article:modified_time"]', 'content', selectedPost?.data?.updated_at || selectedPost?.data?.published_at || selectedPost?.data?.created_at || '')
    let canonical = document.head.querySelector('link[rel="canonical"]')
    if (!canonical) { canonical = document.createElement('link'); canonical.rel = 'canonical'; document.head.appendChild(canonical) }
    canonical.href = canonicalUrl
    let schema = document.getElementById('fanheat-structured-data')
    if (!schema) { schema = document.createElement('script'); schema.id = 'fanheat-structured-data'; schema.type = 'application/ld+json'; document.head.appendChild(schema) }
    schema.textContent = JSON.stringify(selectedPost ? { '@context': 'https://schema.org', '@type': 'Article', headline: selectedPost.title, description, image: [image], keywords: tags, inLanguage: 'ko-KR', author: { '@type': 'Person', name: selectedPost.data?.author_display_name || 'FANHEAT Fan' }, publisher: { '@type': 'Organization', name: 'FANHEAT', logo: { '@type': 'ImageObject', url: `${origin}/images/fanheat-logo.png` } }, mainEntityOfPage: canonicalUrl, datePublished: selectedPost.data?.published_at || selectedPost.data?.created_at, dateModified: selectedPost.data?.updated_at || selectedPost.data?.published_at || selectedPost.data?.created_at } : selectedStar ? { '@context': 'https://schema.org', '@type': 'ProfilePage', name: title, description, url: canonicalUrl, mainEntity: { '@type': 'MusicGroup', name: selectedStar.name, image, description } } : { '@context': 'https://schema.org', '@type': 'WebSite', name: 'FANHEAT', alternateName: ['팬히트', 'Fan Heat'], url: canonicalUrl, description, inLanguage: ['ko-KR', 'en', 'ja'], potentialAction: { '@type': 'SearchAction', target: `${origin}/?q={search_term_string}`, 'query-input': 'required name=search_term_string' } })
  }, [selectedStar, selectedPost, artistDirectory])
  const submitPost = async () => {
    if (!user) { setAuthOpen(true); return }
    try {
      if (editingPost) await updatePost(editingPost.data.id, draft, user, draftImageFiles, draftImages, draftInlineImageFiles, draftInlineImages)
      else await publishPost(draft, user, draftImageFiles, draftImages, draftInlineImageFiles, draftInlineImages)
      const nextHome = await loadHomeData()
      setHome(nextHome)
      setWriting(false)
      if (editingPost) {
        const updatedIndex = nextHome.posts.findIndex(([, , data]) => data.id === editingPost.data.id)
        const updatedPost = nextHome.posts[updatedIndex]
        setSelectedPost(updatedPost ? { title: updatedPost[0], image: updatedPost[1], index: updatedIndex, data: updatedPost[2] } : null)
      }
      setEditingPost(null)
    } catch (error) { setDataNotice(`글 저장 실패: ${error.message}`) }
  }
  const filterAuthors = [...new Set(home.posts.map(([, , data]) => String(data?.author_display_name || 'FANHEAT').trim()))]
  const trendingKeywords = useMemo(() => trendingPostKeywords(home.posts), [home.posts])
  const selectedPostIndex = selectedPost ? home.posts.findIndex(([, , data], index) => data?.id ? data.id === selectedPost.data?.id : index === selectedPost.index) : -1
  const postAt = index => {
    const item = home.posts[index]
    return item ? { title: item[0], image: item[1], index, data: item[2] || {} } : null
  }
  const previousPost = selectedPostIndex > 0 ? postAt(selectedPostIndex - 1) : null
  const nextPost = selectedPostIndex >= 0 && selectedPostIndex < home.posts.length - 1 ? postAt(selectedPostIndex + 1) : null
  const navigatePost = post => {
    setSelectedPost(post)
    if (post?.data?.id) window.history.pushState({}, '', `/posts/${post.data.id}`)
    window.requestAnimationFrame(() => document.querySelector('.post-detail')?.scrollTo({ top: 0, left: 0, behavior: 'auto' }))
  }
  const updatePostHeat = (postId, voteCount) => {
    if (!postId) return
    setHome(current => ({ ...current, posts: current.posts.map(([title, image, data]) => [title, image, data?.id === postId ? { ...data, vote_count: voteCount } : data]) }))
    setSelectedPost(current => current?.data?.id === postId ? { ...current, data: { ...current.data, vote_count: voteCount } } : current)
  }
  const openPostDetail = post => {
    setSelectedPost(post)
    if (!post?.data?.id) return
    if (postPathId() !== post.data.id) window.history.pushState({}, '', `/posts/${post.data.id}`)
    recordPostView(post.data.id).then(viewCount => {
      if (!Number.isFinite(viewCount)) return
      setHome(current => ({ ...current, posts: current.posts.map(([title, image, data]) => [title, image, data?.id === post.data.id ? { ...data, view_count: viewCount } : data]) }))
      setSelectedPost(current => current?.data?.id === post.data.id ? { ...current, data: { ...current.data, view_count: viewCount } } : current)
    }).catch(() => {})
  }
  const bestArtistItems = home.artists.length
    ? home.artists.slice(0, 50).map((artist, index) => [artist.name_ko || artist.name, Number(artist.follower_count || 0).toLocaleString(), artist.image_url || highResolutionFallbacks[index % highResolutionFallbacks.length], artist])
    : home.awards.slice(0, 50)
  const mobileActive = mobileVoteOpen ? 'vote' : writing ? 'write' : myPage ? 'my' : artistDirectory || selectedStar ? 'artists' : 'home'
  const openArtistDirectory = () => { setMobileVoteOpen(false); setWriting(false); setEditingPost(null); setSelectedPost(null); setSelectedStar(null); setSelectedFan(null); setMyPage(false); setQuery(''); setArtistDirectory(true) }
  return <div className={`app ${USER_MUSIC_PLAYBACK_ENABLED ? '' : 'music-playback-disabled'} ${writing ? 'writing-view' : ''} ${menuOpen ? 'mobile-menu-open' : ''} ${mobileVoteOpen ? 'mobile-vote-page-open' : ''} ${myPage ? `my-page-view my-page-mobile-${myPageMobileSection} ${myPageMobileSection === 'profile' ? 'my-page-mobile-profile' : 'my-page-mobile-content'}` : ''}`} id="top" onScrollCapture={revealTransientScrollbar}>
    {writing
      ? <div className="detail-shell compose-shell"><ComposerPreview draft={draft} images={draftImages} /></div>
      : selectedPost
      ? <div className="detail-shell"><PostDetail post={selectedPost} onClose={goHome} user={user} onLogin={() => setAuthOpen(true)} onEdit={openPostEditor} previousPost={previousPost} nextPost={nextPost} onNavigate={navigatePost} onHeatChange={updatePostHeat} onOpenAuthor={openFanPage} /></div>
      : selectedStar
      ? <StarVisual star={selectedStar} onClose={goHome} user={user} onLogin={() => setAuthOpen(true)} />
      : myPage
      ? <MyPageProfile user={user} profile={selectedFan} tracks={home.tracks} onBack={goHome} />
      : <div className={`left-shell ${chartCollapsed ? 'chart-collapsed' : ''}`} id="chart"><ChartPanel onPlay={setSongIndex} activeSong={songIndex} songPlaying={songPlaying} items={home.tracks} artists={home.artists} collapsed={chartCollapsed} onToggle={() => setChartCollapsed(value => !value)} user={user} onLogin={() => setAuthOpen(true)} /><Hero user={user} onLogin={() => setAuthOpen(true)} slides={home.heroSlides} /></div>}
    <main className={`content ${writing ? 'writing-content' : ''} ${selectedStar ? 'star-content' : ''} ${myPage ? 'my-content' : ''} ${artistDirectory ? 'artist-directory-content' : ''}`}><SharedHeader {...{query, setQuery, trendingKeywords, menuOpen, setMenuOpen, writing, user, unreadMessageCount, searchFilters, setSearchFilters, filterAuthors}} loggedIn={Boolean(user)} onLogin={() => setAuthOpen(true)} onWrite={openWriter} onHome={goHome} onMyPage={openMyPage} onLogout={logout} />{dataNotice && <div className="data-notice">{dataNotice}</div>}{writing ? <WriteEditor draft={draft} setDraft={setDraft} images={draftImages} setImages={setDraftImages} imageFiles={draftImageFiles} setImageFiles={setDraftImageFiles} inlineImages={draftInlineImages} setInlineImages={setDraftInlineImages} inlineImageFiles={draftInlineImageFiles} setInlineImageFiles={setDraftInlineImageFiles} onClose={closeWriter} onPublish={submitPost} editing={Boolean(editingPost)} /> : selectedStar ? <StarPage star={selectedStar} onOpenFan={openFanPage} onClose={goHome} user={user} onLogin={() => setAuthOpen(true)} /> : myPage ? <MyPageContent user={user} publicProfile={selectedFan} posts={home.posts} followers={home.awards} unreadMessageCount={unreadMessageCount} initialTab={myPageTab} onUnreadChange={setUnreadMessageCount} onOpenFriend={openFanPage} onSelect={post => { setMyPage(false); setSelectedFan(null); openPostDetail(post) }} /> : artistDirectory ? <ArtistDirectory items={bestArtistItems} query={query} setQuery={setQuery} onClose={() => { setArtistDirectory(false); setQuery('') }} onSelect={star => { recordArtistClick(star.id).catch(() => {}); setArtistDirectory(false); setSelectedPost(null); setSelectedStar(star) }} /> : <><Awards items={bestArtistItems} rankings={home.artistRankings} onViewAll={() => { setQuery(''); setArtistDirectory(true) }} onSelect={star => { setSelectedPost(null); setSelectedStar(star) }} /><Feed query={query} filters={searchFilters} onSelect={openPostDetail} items={home.posts} user={user} onLogin={() => setAuthOpen(true)} onHeatChange={updatePostHeat} /></>}</main>
    {USER_MUSIC_PLAYBACK_ENABLED && !writing && !selectedPost && !myPage && <Player songIndex={songIndex} onSelectSong={setSongIndex} onPlayingChange={setSongPlaying} onClose={() => { setSongPlaying(false); setSongIndex(null) }} items={home.tracks} />}
    {myPage && !selectedFan && <MobileMyPageTabs active={myPageMobileSection} unreadMessageCount={unreadMessageCount} onSelect={selectMyPageMobileSection} onBack={goHome} />}
    {mobileVoteOpen && <MobileVotePage onClose={goHome} onPlay={setSongIndex} activeSong={songIndex} items={home.tracks} artists={home.artists} user={user} onLogin={() => { setMobileVoteOpen(false); setAuthOpen(true) }} />}
    <MobileAppNav active={mobileActive} hidden={Boolean(selectedPost) || (!mobileNavVisible && !mobileVoteOpen)} onHome={goHome} onArtists={openArtistDirectory} onVote={() => { if (user) { setMobileNavVisible(true); setMobileVoteOpen(true); window.scrollTo({ top: 0 }) } else setAuthOpen(true) }} onWrite={() => { setMobileVoteOpen(false); openWriter() }} onMyPage={() => { setMobileVoteOpen(false); openMyPage() }} />
    {authOpen && <AuthModal onClose={() => setAuthOpen(false)} />}
  </div>
}

export default function App() {
  if (window.location.pathname.startsWith('/admin')) return <AdminApp />
  if (window.location.pathname.startsWith('/legal/') || window.location.pathname === '/support') return <LegalPage />
  return <I18nProvider><FanHeatApp /></I18nProvider>
}
