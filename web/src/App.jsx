import { useEffect, useRef, useState } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import Youtube from '@tiptap/extension-youtube'
import DOMPurify from 'dompurify'
import { supabase } from './lib/supabase'
import { addComment, castDailyArtistVote, deleteComment, loadCommentReactions, loadComments, loadDailyArtistVotes, loadHomeData, loadUserComments, publishPost, setCommentReaction, updateComment } from './lib/api'
import { I18nProvider, useI18n } from './i18n'
import './hero-carousel.css'
import './list-number.css'
import './star-page.css'
import './my-page.css'

const A = 'https://yuiemljibxeoifupvluc.supabase.co/storage/v1/object/public/fanheat-assets/3207765e-4d0a-4c9c-b620-46a805ca0ee7/system/'
const assetSrc = value => /^https?:\/\//.test(value || '') ? value : `${A}${value}`
const youtubeEmbedUrl = value => {
  if (!value) return ''
  try {
    const url = new URL(value)
    const id = url.hostname.includes('youtu.be') ? url.pathname.slice(1) : url.searchParams.get('v') || (url.pathname.startsWith('/embed/') ? url.pathname.split('/')[2] : '')
    return /^[A-Za-z0-9_-]{6,15}$/.test(id || '') ? `https://www.youtube-nocookie.com/embed/${id}` : ''
  } catch { return '' }
}
const safeRichHtml = value => DOMPurify.sanitize(value || '', { ADD_TAGS: ['iframe'], ADD_ATTR: ['allow', 'allowfullscreen', 'frameborder', 'data-youtube-video'] })
const highResolutionFallbacks = ['rescene-jacket.jpeg', 'ive-jacket.jpeg', 'bingle_bangle.jpg', 'mypage.jpg', 'rescene-bg.jpeg', 'ive-bg.jpeg', 'post2.jpg', 'mypage_bg.jpg']
const postDetailFallbacks = [
  ['rescene-jacket.jpeg', 'rescene-bg.jpeg', 'mypage.jpg'],
  ['post2.jpg', 'rescene-jacket.jpeg', 'ive-jacket.jpeg'],
  ['ive-jacket.jpeg', 'ive-bg.jpeg', 'bingle_bangle.jpg'],
  ['mypage.jpg', 'mypage_bg.jpg', 'post2.jpg'],
]

const charts = [
  ['Way Back Home', '숀 (SHAUN)', 'chart1.jpg'],
  ['SQUARE UP', 'BLACKPINK', 'chart2.jpg'],
  ['Summer Nights', 'TWICE(트와이스)', 'chart3.jpg'],
  ['RED MOON', '마마무(Mamamoo)', 'chart4.jpg'],
  ['ONE & SIX', 'Apink (에이핑크)', 'chart5.jpg'],
  ['Blooming Blue', '청하', 'chart6.jpg'],
  ['여행', '볼빨간사춘기', 'chart7_2.jpg'],
  ['Forever Young', 'BLACKPINK', 'chart8.jpg'],
  ['키스 먼저 할까요', '폴킴', 'chart9.jpg'],
  ['The Fairy Tale', '멜로망스', 'chart10.jpg'],
  ['THIS IS US', '비투비', 'chart11.jpg'],
  ['지나오다', '닐로', 'chart12.jpg'],
]

const awards = [
  ['워너원', '158,254', 'award1.jpg'],
  ['아이유', '121,001', 'award2.jpg'],
  ['빅뱅', '91,447', 'award3.jpg'],
  ['씨스타', '62,221', 'award4.jpg'],
  ['트와이스', '58,912', 'award1.jpg'],
  ['레드벨벳', '52,430', 'award2.jpg'],
  ['엑소', '49,118', 'award3.jpg'],
  ['블랙핑크', '45,702', 'award4.jpg'],
]

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

const makeStarProfile = ([name, score, image, data]) => {
  const copy = starCopy[name] || { realName: name, role: 'K-POP 아티스트', debut: '공식 프로필 확인', agency: '소속사 정보', fandom: 'FAN HEAT' }
  const gallery = [...new Set([...(data?.gallery_images || []), ...(starGalleryFallbacks[name] || []), copy.heroImage, image].filter(Boolean))].slice(0, 3)
  return { ...copy, id: data?.id || name, name, image, gallery, followers: Number(String(score).replace(/,/g, '')) || 0, bio: copy.bio || [`${name}은(는) 전 세계 팬들과 음악으로 소통하며 개성 있는 무대와 콘텐츠를 선보이는 K-POP 아티스트입니다.`, `FAN HEAT에서 ${name}의 새로운 앨범과 팬 소식, 공연 일정을 한곳에서 확인하고 함께 이야기를 나눌 수 있습니다.`] }
}

const posts = [
  ['설리 비키니 + 딸기', 'post_list1.jpg'],
  ['트와이스 사나', 'post_list2.jpg'],
  ['레드벨벳 슬기 웬디 - 배틀트립', 'post_list3.jpg'],
  ['프로듀스48 연습생 - 김도아', 'post_list4.jpg'],
  ['7월 27일 치바 에리이 트위터 사진', 'post_list5.jpg'],
  ['하니의 에나멜 의상 뒷태', 'post_list6.jpg'],
  ['모모랜드 데이지', 'post_list7.jpg'],
  ['설리 비키니 + 딸기', 'post_list1.jpg'],
  ['트와이스 사나', 'post_list2.jpg'],
  ['레드벨벳 슬기 웬디 - 배틀트립', 'post_list3.jpg'],
]

const postSlides = posts.map(([title, image], index) => [
  image,
  posts[(index + 1) % posts.length][1],
  posts[(index + 2) % posts.length][1],
])

const voteCounts = [28, 76, 184, 430, 1280, 356, 92, 2640, 5820, 12840]

function ChartPanel({ onPlay, activeSong, items = charts, artists = [], collapsed, onToggle, user, onLogin }) {
  const { t, localizeTitle } = useI18n()
  const [voteMode, setVoteMode] = useState(false)
  const [voteQuery, setVoteQuery] = useState('')
  const [selectedVote, setSelectedVote] = useState(null)
  const [dailyCounts, setDailyCounts] = useState({})
  const [ownVote, setOwnVote] = useState(null)
  const [votePending, setVotePending] = useState(false)
  const [voteMessage, setVoteMessage] = useState('')
  useEffect(() => {
    if (!voteMode) return
    loadDailyArtistVotes(user?.id).then(({ counts, ownVote: voted }) => { setDailyCounts(counts); setOwnVote(voted) }).catch(error => setVoteMessage(error.message))
  }, [voteMode, user?.id])
  const openVoting = () => { if (!user) { onLogin(); return }; setVoteMode(value => !value); setSelectedVote(null); setVoteQuery(''); setVoteMessage('') }
  const voteItems = voteQuery.trim() ? artists.filter(artist => `${artist.name} ${artist.name_ko || ''}`.toLowerCase().includes(voteQuery.trim().toLowerCase())).map(artist => [artist.name_ko || artist.name, artist.name, artist.image_url, { artist_id: artist.id }]) : items
  const submitVote = async () => {
    if (!selectedVote || !user || ownVote) return
    setVotePending(true); setVoteMessage('')
    try { const result = await castDailyArtistVote(user.id, selectedVote.data.artist_id); setDailyCounts(result.counts); setOwnVote(result.ownVote); setSelectedVote(null); setVoteMode(false) }
    catch (error) { setVoteMessage(error.code === '23505' ? '오늘의 투표는 이미 완료했습니다.' : error.message) }
    finally { setVotePending(false) }
  }
  return <aside className={`chart-panel ${collapsed ? 'collapsed' : ''}`}>
    <div className="brand-tile">
      <button className="back-button" onClick={onToggle} aria-label={collapsed ? '순위 목록 펼치기' : '순위 목록 접기'} aria-expanded={!collapsed}><span>{collapsed ? '→' : '←'}</span></button>
      <img src={`${A}fanheat-logo.png`} alt="FAN HEAT" />
      {voteMode && <label className="vote-search"><input value={voteQuery} onChange={event => setVoteQuery(event.target.value)} placeholder="가수 검색" autoFocus /><span>⌕</span></label>}
      {!voteMode && <button className={`vote-button ${ownVote ? 'complete' : ''}`} onClick={openVoting}>{ownVote ? '1Day 투표 완료' : t('voteDay')}</button>}
    </div>
    <ol className={`chart-list ${voteMode ? 'voting' : ''}`}>
      {voteItems.map(([title, artist, image, data = {}], index) => <li key={`${data.artist_id || title}-${index}`} className={`${activeSong === index && !voteMode ? 'playing' : ''} ${voteMode && selectedVote?.data.artist_id === data.artist_id ? 'vote-selected' : ''}`.trim()}>
        <button onClick={() => voteMode ? setSelectedVote({ title, artist, image, data }) : onPlay(index)} aria-label={voteMode ? `${title} 투표 선택` : `${title} 재생`}>
          <span className="rank">{String(index + 1).padStart(2, '0')}</span>
          <span className="cover"><img src={assetSrc(image)} alt={`${title} 커버`} /><b className={`compact-rank rank-${index + 1}`}>{index + 1}위</b><i>{activeSong === index ? 'Ⅱ' : '▶'}</i></span>
          <span className="song"><strong>{localizeTitle(title)}</strong><small>{artist}</small></span>
          {voteMode && <span className={`vote-check ${selectedVote?.data.artist_id === data.artist_id ? 'selected' : ''}`}>✓</span>}
        </button>
      </li>)}
      {voteMode && selectedVote && <div className="vote-confirm" role="dialog" aria-modal="true" aria-label="가수 투표 확인"><img src={assetSrc(selectedVote.image)} alt="" /><h3>{selectedVote.title}</h3><p>{selectedVote.artist}</p><span>Today</span><strong>{(dailyCounts[selectedVote.data.artist_id] || 0).toLocaleString()}<small>표</small></strong>{voteMessage && <em>{voteMessage}</em>}<div><button onClick={submitVote} disabled={votePending || Boolean(ownVote)}>{ownVote ? '오늘 투표 완료' : votePending ? '처리 중' : '투표'}</button><button onClick={() => setSelectedVote(null)}>취소</button></div></div>}
    </ol>
    {voteMode && <div className="vote-cancel-bar"><button type="button" onClick={openVoting}>투표 취소</button></div>}
  </aside>
}

function Hero() {
  const slides = [
    ['bingle_bangle.jpg', 'bg_hyuna.jpg', 'AOA · Bingle Bangle', 'AOA 5TH MINI ALBUM · BINGLE BANGLE'],
    ['rescene-jacket.jpeg', 'rescene-bg.jpeg', 'RESCENE · Pretty Girl', '2026 SPECIAL SINGLE · PRETTY GIRL'],
    ['ive-jacket.jpeg', 'ive-bg.jpeg', 'IVE · REVIVE+', 'IVE THE 2ND ALBUM · BLACKHOLE'],
  ]
  const [active, setActive] = useState(0)
  const [paused, setPaused] = useState(false)
  useEffect(() => {
    if (paused) return undefined
    const timer = setInterval(() => setActive(current => (current + 1) % slides.length), 5000)
    return () => clearInterval(timer)
  }, [paused, slides.length])
  return <section className="hero" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
    <div className="hero-backgrounds" aria-hidden="true">{slides.map(([, background], index) => <div key={background} className={active === index ? 'active' : ''} style={{ backgroundImage: `linear-gradient(135deg,rgba(101,44,148,.76),rgba(16,143,219,.78)),url(${assetSrc(background)})` }} />)}</div>
    <div className="hero-carousel">
      <div className="hero-track" style={{ transform: `translate3d(-${active * 100}%,0,0)` }}>{slides.map(([image, , title, caption]) => <article className="album-card" key={image}>
        <img src={assetSrc(image)} alt={title} />
        <p><strong>{title}</strong><span>{caption}</span></p>
      </article>)}</div>
      <div className="hero-dots">{slides.map((_, index) => <button key={index} className={active === index ? 'active' : ''} onClick={() => setActive(index)} aria-label={`${index + 1}번째 재킷`} />)}</div>
    </div>
  </section>
}

function Header({ query, setQuery, menuOpen, setMenuOpen, loggedIn, user, onLogin, onWrite, onHome, onMyPage, onLogout, writing }) {
  const { locale, setLocale, t } = useI18n()
  const [profileOpen, setProfileOpen] = useState(false)
  const profileMenu = useRef(null)
  useEffect(() => {
    const close = event => { if (!profileMenu.current?.contains(event.target)) setProfileOpen(false) }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [])
  const displayName = user?.user_metadata?.display_name || user?.email?.split('@')[0] || 'FAN'
  return <header className="topbar">
    <a className="mobile-logo" href="#top" onClick={onHome} aria-label="FAN HEAT 홈">
      <span className="header-brand-mark" aria-hidden="true"><i>☆</i><b>FAN HEAT</b></span>
    </a>
    <form className="search" onSubmit={e => e.preventDefault()}>
      <span>⌕</span><input value={query} onChange={e => setQuery(e.target.value)} placeholder={t('search')} aria-label={t('search')} />
    </form>
    <div className="keywords"><span>›</span> 워너원, 공항패션, 직촬</div>
    <nav className={menuOpen ? 'open' : ''}>
      <label className="language-picker" aria-label={t('language')}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.7 2.5 4 5.5 4 9s-1.3 6.5-4 9c-2.7-2.5-4-5.5-4-9s1.3-6.5 4-9Z"/></svg><select value={locale} onChange={event => setLocale(event.target.value)}><option value="ko">KO</option><option value="en">EN</option><option value="ja">JPN</option></select></label>
      {loggedIn ? <div className="profile-actions"><button className={`write-button ${writing ? 'active' : ''}`} onClick={onWrite}>{writing ? t('writing') : t('write')}</button><div className="profile-menu-wrap" ref={profileMenu}><button className="profile-button" onClick={() => setProfileOpen(value => !value)} aria-expanded={profileOpen} aria-haspopup="menu" aria-label="프로필 퀵 메뉴"><img src={assetSrc(user?.user_metadata?.avatar_url || 'mypage.jpg')} alt="" /><i>1</i></button>{profileOpen && <div className="profile-quick-menu profile-account-menu" role="menu"><p className="profile-menu-caption">현재 로그인 계정</p><header><img src={assetSrc(user?.user_metadata?.avatar_url || 'mypage.jpg')} alt="" /><strong>{displayName}</strong></header><section><h3>내 계정</h3><button role="menuitem" onClick={() => { setProfileOpen(false); onMyPage() }}>마이 페이지</button><button role="menuitem" onClick={() => setProfileOpen(false)}>설정</button></section><section><h3>콘텐츠</h3><button role="menuitem" onClick={() => { setProfileOpen(false); onWrite() }}>새 글 작성</button><button role="menuitem" onClick={() => { setProfileOpen(false); onMyPage() }}>내 포스트와 북마크</button></section><section><h3>도움말</h3><button role="menuitem" onClick={() => setProfileOpen(false)}>도움말 센터 <b aria-hidden="true">↗</b></button><button role="menuitem" onClick={() => setProfileOpen(false)}>기능 요청 <b aria-hidden="true">↗</b></button></section><section><h3>개인정보 보호</h3><button role="menuitem" onClick={() => setProfileOpen(false)}>개인정보처리방침 <b aria-hidden="true">↗</b></button><button role="menuitem" onClick={() => setProfileOpen(false)}>개인정보 보호권</button><button role="menuitem" onClick={() => setProfileOpen(false)}>서비스 약관 <b aria-hidden="true">↗</b></button></section><button className="quick-logout" role="menuitem" onClick={() => { setProfileOpen(false); onLogout() }}>로그아웃</button></div>}</div></div> : <button className="login" onClick={onLogin}>{t('login')}</button>}
    </nav>
    <button className="menu-button" onClick={() => setMenuOpen(v => !v)} aria-expanded={menuOpen} aria-label="메뉴 열기">{menuOpen ? '×' : '☰'}</button>
  </header>
}

function MyPageAudioPlayer({ track, playing, onToggle, onPrevious, onNext }) {
  return <div className="my-audio-player" aria-label="마이 뮤직 플레이어"><button className="my-audio-play" onClick={onToggle} aria-label={playing ? '일시정지' : '재생'}>{playing ? 'Ⅱ' : '▶'}</button><button onClick={onPrevious} aria-label="이전 곡">◀</button><button onClick={onNext} aria-label="다음 곡">▶</button><button aria-label="음량">🔊</button><button aria-label="다운로드">⬇</button><img src={assetSrc(track[0])} alt="" /><div><strong>{track[1]}</strong><span>{track[2]}</span></div><time><b>00:46</b><small>04:05</small></time><button aria-label="재생목록">☰</button></div>
}

function MyPageProfile({ user }) {
  const profileSlides = ['mypage.jpg', 'chart1.jpg', 'post_list4.jpg']
  const music = [['music1.jpg','싸이렌 (Siren)','선미 / WARNING'],['music2.jpg','NOAH (Feat. 박재범, Hoody)','HAON / TRAVEL : NOAH'],['music3.jpg','몰랐니 (Lil’ Touch)','소녀시대-Oh!GG'],['music4.jpg','IDOL','방탄소년단'],['music5.jpg','Way Back Home','숀 (SHAUN)']]
  const [slide, setSlide] = useState(0)
  const [trackIndex, setTrackIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const audio = useRef(null)
  const toggleAudio = () => { if (playing) audio.current?.pause(); else audio.current?.play().catch(() => {}); setPlaying(value => !value) }
  const chooseTrack = index => { setTrackIndex(index); setPlaying(true); requestAnimationFrame(() => { if (audio.current) { audio.current.currentTime = 0; audio.current.play().catch(() => setPlaying(false)) } }) }
  const moveTrack = direction => chooseTrack((trackIndex + direction + music.length) % music.length)
  const nickname = user?.user_metadata?.display_name || user?.email?.split('@')[0] || 'FANHEAT'
  return <section className="my-page-profile"><audio ref={audio} src="/sample.mp3" loop /><div className="my-cover" style={{ backgroundImage: `linear-gradient(90deg,rgba(11,9,16,.83),rgba(10,8,15,.28)),url(${assetSrc('mypage_bg.jpg')})` }}><div className="my-cover-copy"><h1>{nickname}</h1><button>♥ FOLLOW</button><button className="my-edit">정보수정</button><p>좋아하는 음악과 아티스트의 순간을 모아 팬들과 함께 나누고 있습니다.</p><span>K-POP FAN</span><div><button>f</button><button>𝕏</button><button>◎</button></div></div><button className="my-cover-play" onClick={toggleAudio} aria-label={playing ? '대표 음원 일시정지' : '대표 음원 재생'}>{playing ? 'Ⅱ' : '▶'}</button></div><div className="my-avatar-carousel"><button onClick={() => setSlide((slide - 1 + profileSlides.length) % profileSlides.length)} aria-label="이전 프로필">‹</button><img src={assetSrc(profileSlides[slide])} alt="내 프로필" /><button onClick={() => setSlide((slide + 1) % profileSlides.length)} aria-label="다음 프로필">›</button><div>{profileSlides.map((_, index) => <i key={index} className={slide === index ? 'active' : ''} />)}</div></div><div className="my-profile-body"><section className="my-resources"><article><header><strong>Voting Mana</strong><span>80%</span></header><div><i style={{ width: '80%' }} /></div></article><article><header><strong>Resource Credits</strong><span>80%</span></header><div><i style={{ width: '80%' }} /></div></article><dl><div><dt>Lv</dt><dd>10</dd></div><div><dt>SP</dt><dd>01. (+14.94) HEAT</dd></div><div><dt>CR</dt><dd>0.001 CREDIT</dd></div></dl></section><p className="my-intro">음악과 무대를 사랑하는 FAN HEAT 사용자입니다. 새로운 앨범과 공연 소식을 발견하고, 좋아하는 아티스트에 대한 이야기를 팬들과 함께 나눕니다.</p><section className="my-music"><header><h2>My뮤직</h2><span>Total : {music.length}</span></header>{music.map((item, index) => <button key={item[1]} className={trackIndex === index ? 'active' : ''} onClick={() => chooseTrack(index)}><b>{index + 1}</b><img src={assetSrc(item[0])} alt="" /><span><strong>{item[1]}</strong><small>{item[2]}</small></span><em>{trackIndex === index && playing ? 'Ⅱ' : '▶'}</em></button>)}</section></div><MyPageAudioPlayer track={music[trackIndex]} playing={playing} onToggle={toggleAudio} onPrevious={() => moveTrack(-1)} onNext={() => moveTrack(1)} /></section>
}

function MyPageContent({ user, posts: items, followers, onSelect }) {
  const [tab, setTab] = useState('posts')
  const [sort, setSort] = useState('latest')
  const [myComments, setMyComments] = useState([])
  const [commentError, setCommentError] = useState('')
  useEffect(() => {
    let active = true
    if (!user?.id) return undefined
    loadUserComments(user.id).then(rows => { if (active) { setMyComments(rows); setCommentError('') } }).catch(error => { if (active) setCommentError(error.message) })
    return () => { active = false }
  }, [user?.id])
  const owned = items.filter(([, , data]) => data?.author_id === user?.id)
  const visiblePosts = (owned.length ? owned : items).slice(0, tab === 'bookmarks' ? 5 : 8)
  const sortedPosts = sort === 'popular' ? [...visiblePosts].sort((a, b) => (b[2]?.vote_count || 0) - (a[2]?.vote_count || 0)) : visiblePosts
  const tabs = [['posts','POST',owned.length || visiblePosts.length],['bookmarks','BOOKMARK',Math.min(5, items.length)],['followers','FOLLOWERS',followers.length],['comments','COMMENT',myComments.length]]
  const commentItems = myComments.map(comment => {
    const item = items.find(([, , data]) => data?.id === comment.post_id)
    return { comment, item }
  })
  return <section className="my-page-content"><div className="my-page-tabs">{tabs.map(([key, label, count]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}<b>{count}</b></button>)}<label>정렬기준<select value={sort} onChange={event => setSort(event.target.value)}><option value="latest">최신순</option><option value="popular">보상점수</option></select></label></div>{tab === 'followers' ? <div className="my-followers">{followers.slice(0, 8).map(([name, score, image], index) => <article key={`${name}-${index}`}><img src={assetSrc(image)} alt="" /><div><strong>{name}</strong><p>{Number(String(score).replace(/,/g, '')).toLocaleString()}명의 팬이 함께하고 있습니다.</p></div><button>팔로우</button></article>)}</div> : tab === 'comments' ? <div className="my-comment-history">{commentError && <p className="my-comment-empty">댓글을 불러오지 못했습니다: {commentError}</p>}{!commentError && !commentItems.length && <p className="my-comment-empty">아직 작성한 댓글이 없습니다.</p>}{commentItems.map(({ comment, item }, index) => { const [title = '삭제되었거나 비공개된 포스트', image = 'post_list1.jpg', data = {}] = item || []; return <button key={comment.id} onClick={() => item && onSelect({ title, image, index: items.indexOf(item), data, editCommentId: comment.id })} disabled={!item}><span className="my-comment-rank">{String(index + 1).padStart(2, '0')}</span><img src={assetSrc(image)} alt="" /><span className="my-comment-copy"><small>내가 댓글을 남긴 포스트</small><strong>{title}</strong><q>{comment.body}</q></span><time>{new Date(comment.created_at).toLocaleString('ko-KR', { dateStyle: 'medium', timeStyle: 'short' })}</time><em>수정하기 ›</em></button> })}</div> : <div className="my-post-list">{sortedPosts.map((item, index) => { const [title, image, data] = item; return <article key={data?.id || `${title}-${index}`} onClick={() => onSelect({ title, image, index, data })} tabIndex="0"><span className="my-post-rank">{index + 1}<i>•••</i></span><img src={assetSrc(image)} alt="" /><div><h3>{title}</h3><p>{data?.summary || 'K-POP 팬들이 함께 나누는 아티스트의 새로운 소식입니다.'}</p><small>조회 {(data?.view_count || 1200).toLocaleString()}　♛ 15　▱ 3</small></div><time>{new Date(data?.created_at || Date.now()).toLocaleDateString('ko-KR')}</time><HeatVote initialCount={data?.vote_count || voteCounts[index] || 28} /></article> })}</div>}</section>
}

function Awards({ items = awards, onSelect, onViewAll }) {
  const { t } = useI18n()
  const [period, setPeriod] = useState('Weeks')
  const [page, setPage] = useState(0)
  const [pageCount, setPageCount] = useState(2)
  const [paused, setPaused] = useState(false)
  const track = useRef(null)
  const measure = () => {
    if (!track.current) return
    const card = track.current.querySelector('article')
    if (!card) return
    const gap = 8
    const visible = Math.max(1, Math.floor((track.current.clientWidth + gap) / (card.getBoundingClientRect().width + gap)))
    setPageCount(Math.max(1, Math.ceil(items.length / visible)))
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
  }, [])
  useEffect(() => {
    if (paused || pageCount < 2) return undefined
    const timer = setInterval(() => goTo(page + 1), 4500)
    return () => clearInterval(timer)
  }, [page, pageCount, paused])
  return <section className="awards" id="awards">
    <div className="section-head"><div className="section-title"><h2>{t('awards')}</h2><button className="view-all-artists" onClick={onViewAll}>전체 보기 <span>›</span></button></div>
      <div className="periods">{[['Today','today'], ['Weeks','weeks'], ['Month','month']].map(([item,key]) => <button className={period === item ? 'active' : ''} onClick={() => setPeriod(item)} key={item}>{t(key)}</button>)}</div>
    </div>
    <div className="award-carousel" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <button className="award-arrow prev" onClick={() => goTo(page - 1)} aria-label="이전 어워즈">‹</button>
      <div className="award-grid" ref={track}>{items.map((item, index) => { const [name, score, image] = item; return <article key={`${name}-${index}`}>
        <button className="award-card" onClick={() => onSelect?.(makeStarProfile(item))} aria-label={`${name} 스타 페이지 보기`}>
          <span className="award-image"><img src={assetSrc(image)} alt={name} /></span>
          <span className="award-caption"><strong><i>{index + 1}위</i> {name}</strong><small>{score}</small></span>
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
      {visible.map((item, index) => { const [name, score, image, data] = item; const originalIndex = items.indexOf(item); const hasMaster = Boolean(data?.master_user_id || data?.master_id || data?.has_master || [0, 3, 6, 9].includes(originalIndex)); return <button className={`artist-directory-card artist-palette-${originalIndex % 8}`} key={data?.id || `${name}-${index}`} onClick={() => onSelect(makeStarProfile(item))}>
        <span className="artist-card-top"><b>★ FAN HEAT</b><small>ARTIST PAGE</small><i>{String(originalIndex + 1).padStart(2, '0')}</i></span>
        <span className="artist-card-body">
          <span className="artist-card-left"><span className="artist-directory-image"><img src={assetSrc(image)} alt={name} /></span><span className="artist-card-stat"><small>FANS</small><strong>{score === 'FAN HEAT' ? 'OFFICIAL' : score}</strong></span><span className="artist-card-genre"><small>GENRE</small><strong>K-POP</strong></span></span>
          <span className="artist-directory-copy"><span className="artist-card-heading">TOP ARTIST</span><span className="artist-directory-name"><strong>{name}</strong>{hasMaster && <span className="artist-master-badge" title="FAN HEAT 관리자에게 승인된 아티스트 마스터"><i aria-hidden="true">◆</i> MASTER</span>}</span><small>{data?.name && data.name !== name ? data.name : 'K-POP ARTIST'}</small><span className="artist-card-label">TOP CONTENT</span><em><span>새 소식</span><span>앨범</span><span>팬 커뮤니티</span><span>공연 일정</span></em></span>
        </span>
        <b className="artist-card-open" aria-hidden="true">↗</b>
      </button> })}
    </div>
    {!visible.length && <div className="artist-directory-empty"><strong>검색 결과가 없습니다.</strong><span>다른 가수명이나 그룹명으로 검색해 보세요.</span></div>}
  </section>
}

function StarVisual({ star, onClose }) {
  const [liked, setLiked] = useState(false)
  const profileImages = (star.gallery?.length ? star.gallery : [star.heroImage || star.image]).slice(0, 3)
  const [profileSlide, setProfileSlide] = useState(0)
  const [profileDirection, setProfileDirection] = useState('next')
  const [profileDragging, setProfileDragging] = useState(false)
  const profileDragStart = useRef(null)
  useEffect(() => { setProfileSlide(0) }, [star.id])
  const showProfileSlide = (next, direction = 'next') => { setProfileDirection(direction); setProfileSlide(next) }
  const finishProfileDrag = event => {
    if (profileDragStart.current === null) return
    const distance = event.clientX - profileDragStart.current
    if (Math.abs(distance) > 18 && profileImages.length > 1) {
      showProfileSlide(distance < 0 ? (profileSlide + 1) % profileImages.length : (profileSlide - 1 + profileImages.length) % profileImages.length, distance < 0 ? 'next' : 'prev')
    }
    profileDragStart.current = null
    setProfileDragging(false)
  }
  return <section className="star-visual" aria-label={`${star.name} 프로필`}>
    <aside className="star-profile">
      <button className="star-back" onClick={onClose} aria-label="메인으로 돌아가기">‹</button>
      <button className={`star-like ${liked ? 'active' : ''}`} onClick={() => setLiked(value => !value)} aria-pressed={liked} aria-label="스타 좋아요">♥</button>
      <div className={`star-avatar-carousel ${profileDragging ? 'dragging' : ''}`} onPointerDown={event => { if (profileImages.length < 2) return; profileDragStart.current = event.clientX; setProfileDragging(true); event.currentTarget.setPointerCapture(event.pointerId) }} onPointerUp={finishProfileDrag} onPointerCancel={finishProfileDrag}>
        <img key={`${profileImages[profileSlide]}-${profileSlide}`} className={`star-avatar ${profileDirection}`} src={assetSrc(profileImages[profileSlide])} alt={`${star.name} 프로필 ${profileSlide + 1}`} draggable="false" />
      </div>
      <div className="star-profile-dots">{profileImages.map((_, index) => <button key={index} className={profileSlide === index ? 'active' : ''} onClick={() => showProfileSlide(index, index >= profileSlide ? 'next' : 'prev')} aria-label={`${index + 1}번째 프로필 이미지`} />)}</div>
      <div className="star-facts"><small>PROFILE</small><h1>{star.realName}</h1><p>{star.role}</p><dl><div><dt>데뷔</dt><dd>{star.debut}</dd></div><div><dt>소속사</dt><dd>{star.agency}</dd></div><div><dt>팬덤</dt><dd>{star.fandom}</dd></div></dl></div>
      <div className="star-followers"><small>FOLLOWER</small><strong>{star.followers.toLocaleString()}</strong><span>명</span></div>
      <div className="star-visitors"><small>VISITOR</small><p>Today : {(star.visitorToday || 454842).toLocaleString()}</p><p>Total : {(star.visitorTotal || 405541258).toLocaleString()}</p></div>
      <div className="star-socials">
        <button className="facebook" aria-label="Facebook"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 8h3V4h-3c-3.3 0-5 2-5 5v2H6v4h3v9h4v-9h3l1-4h-4V9c0-.7.3-1 1-1Z" /></svg></button>
        <button className="twitter" aria-label="Twitter"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M22 5.8c-.7.3-1.5.5-2.3.6.8-.5 1.5-1.3 1.8-2.2-.8.5-1.7.8-2.6 1a4 4 0 0 0-6.9 2.7c0 .3 0 .6.1.9A11.5 11.5 0 0 1 3.7 4.5a4 4 0 0 0 1.3 5.4c-.7 0-1.3-.2-1.8-.5 0 2 1.4 3.7 3.3 4-.4.1-.8.2-1.1.2l-.8-.1a4 4 0 0 0 3.8 2.8A8.2 8.2 0 0 1 3.3 18H2a11.4 11.4 0 0 0 6.2 1.8c7.5 0 11.6-6.2 11.6-11.6v-.5c.8-.5 1.5-1.2 2.2-1.9Z" /></svg></button>
        <button className="instagram" aria-label="Instagram"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5" /><circle cx="12" cy="12" r="4.2" /><circle cx="17.5" cy="6.7" r="1" className="instagram-dot" /></svg></button>
      </div>
    </aside>
    <div className="star-portrait"><img src={assetSrc(star.heroImage || star.image)} alt={`${star.name} 고해상도 대표 이미지`} />{star.imageCredit && <a className="star-image-credit" href={star.imageCreditUrl} target="_blank" rel="noreferrer">Photo: {star.imageCredit}</a>}<div><strong>{star.name}</strong><span>FAN HEAT ARTIST</span></div></div>
  </section>
}

const albumCatalog = [
  ['꽃갈피 둘','잠 못 드는 밤 비는 내리고','2017.09.22','싱글/EP',6,'music1.jpg'],
  ['Palette','팔레트 (Feat. G-DRAGON)','2017.04.21','정규앨범',10,'music2.jpg'],
  ['사랑이 잘','사랑이 잘 (With 오혁)','2017.04.07','싱글/EP',1,'music3.jpg'],
  ['밤편지','밤편지','2017.03.24','싱글/EP',1,'music4.jpg'],
  ['CHAT-SHIRE','스물셋','2015.10.23','미니앨범',7,'music5.jpg'],
  ['마음','마음','2015.05.18','디지털 싱글',2,'music6.jpg'],
  ['소격동','소격동','2014.10.02','싱글/EP',1,'music7.jpg'],
  ['애타는 마음','애타는 마음','2014.06.30','싱글/EP',2,'music8.jpg'],
  ['꽃갈피','나의 옛날이야기','2014.05.16','리메이크 앨범',7,'award1.jpg'],
  ['Modern Times – Epilogue','금요일에 만나요','2013.12.20','정규앨범',15,'award2.jpg'],
  ['Modern Times','분홍신','2013.10.08','정규앨범',13,'award3.jpg'],
  ['스무 살의 봄','하루 끝','2012.05.11','싱글/EP',3,'award4.jpg'],
  ['Last Fantasy','너랑 나','2011.11.29','정규앨범',13,'bingle_bangle.jpg'],
  ['Real+','나만 몰랐던 이야기','2011.02.17','싱글/EP',3,'post2.jpg'],
  ['Real','좋은 날','2010.12.09','미니앨범',6,'post_list1.jpg'],
  ['IU...IM','마쉬멜로우','2009.11.12','미니앨범',7,'post_list2.jpg'],
  ['Growing Up','Boo','2009.04.23','정규앨범',16,'post_list3.jpg'],
  ['Lost and Found','미아','2008.09.23','미니앨범',6,'post_list4.jpg'],
]

function AlbumDetailModal({ star, album, onClose }) {
  const isNightLetter = album.title.includes('밤편지') || album.track.includes('밤편지')
  const videoId = isNightLetter ? 'NnRjwEhFU70' : 'w7EnL9ehpfc'
  const melonUrl = `https://www.melon.com/search/total/index.htm?q=${encodeURIComponent(`${star.name} ${album.title}`)}`
  const trackSeeds = [album.track, 'Opening Scene', 'Moonlight Letter', '우리의 계절', 'Stay With Me', '다시 만나는 날', 'Encore', '별을 따라']
  const tracks = Array.from({ length: Math.max(1, Math.min(album.tracks, 10)) }, (_, index) => ({
    title: trackSeeds[index] || `${album.title} Track ${index + 1}`,
    titleTrack: index === 0,
    views: (154245 + index * 47289).toLocaleString(),
  }))

  useEffect(() => {
    const closeOnEscape = event => { if (event.key === 'Escape') onClose() }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  return <div className="album-modal-overlay" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <section className="album-modal" role="dialog" aria-modal="true" aria-labelledby="album-modal-title">
      <header className="album-modal-head">
        <strong>K-POP Music</strong>
        <div>
          <a className="melon-buy" href={melonUrl} target="_blank" rel="noreferrer"><span>음원 구매</span><b>Melon</b></a>
          <button className="album-modal-close" onClick={onClose} aria-label="앨범 상세 닫기">×</button>
        </div>
      </header>
      <div className="album-modal-grid">
        <div className="album-modal-left">
          <h2 id="album-modal-title">{star.name} · {album.title}</h2>
          <div className="album-summary">
            <img src={assetSrc(album.image)} alt={`${album.title} 앨범 재킷`} />
            <div><h3>{album.title}</h3><dl><div><dt>발매일</dt><dd>{album.date}</dd></div><div><dt>앨범</dt><dd>{album.type}</dd></div><div><dt>곡수</dt><dd>{album.tracks}곡</dd></div><div><dt>아티스트</dt><dd>{star.name}</dd></div></dl></div>
          </div>
          <h3 className="album-subtitle">곡 정보</h3>
          <div className="track-table" role="table" aria-label={`${album.title} 수록곡`}>
            <div className="track-table-head" role="row"><span>번호</span><span>곡 정보</span><span>조회</span><span>영상</span></div>
            {tracks.map((track, index) => <div className="track-row" role="row" key={`${track.title}-${index}`}><span>{index + 1}</span><strong>{track.title}{track.titleTrack && <em>TITLE</em>}</strong><span>{track.views}</span><a href={`https://www.youtube.com/watch?v=${videoId}`} target="_blank" rel="noreferrer" aria-label={`${track.title} YouTube에서 보기`}>▶</a></div>)}
          </div>
        </div>
        <div className="album-modal-right">
          <div className="album-video-title"><h3>{album.track}</h3><span>YouTube</span></div>
          <div className="album-video-frame"><iframe src={`https://www.youtube-nocookie.com/embed/${videoId}`} title={`${star.name} ${album.track} 영상`} allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowFullScreen /></div>
          <div className="album-lyrics-title"><h3>가사</h3><span>LYRICS</span></div>
          <div className="album-lyrics"><p>오늘의 마음을 천천히 펼쳐<br />서로의 빛을 따라 걷는 밤<br />멀리 있어도 들려오는 목소리<br />우리의 계절은 다시 시작돼</p><p>별이 내려앉은 이 길 위에서<br />따뜻한 노래를 함께 불러<br />잊지 못할 순간을 모아<br />내일의 페이지를 채워가</p><small>가사 미리보기는 화면 구성을 위한 데모 콘텐츠입니다.</small></div>
        </div>
      </div>
    </section>
  </div>
}

function StarAlbums({ star }) {
  const [visibleCount, setVisibleCount] = useState(8)
  const [selectedAlbum, setSelectedAlbum] = useState(null)
  const sentinel = useRef(null)
  const catalog = albumCatalog.map((album, index) => ({ id: `${star.id}-${index}`, title: album[0], track: album[1], date: album[2], type: album[3], tracks: album[4], image: highResolutionFallbacks[index % highResolutionFallbacks.length] }))
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
    <div className="album-sentinel" ref={sentinel}>{visibleCount < catalog.length ? <span>앨범을 더 불러오는 중…</span> : catalog.length > 8 ? <span>모든 앨범을 확인했습니다.</span> : null}</div>
    {selectedAlbum && <AlbumDetailModal star={star} album={selectedAlbum} onClose={() => setSelectedAlbum(null)} />}
  </section>
}

function StarPage({ star }) {
  const { locale } = useI18n()
  const [tab, setTab] = useState('intro')
  const labels = { ko: ['소개', '앨범', '콘서트 일정'], en: ['About', 'Albums', 'Concerts'], ja: ['紹介', 'アルバム', 'コンサート'] }[locale] || ['소개', '앨범', '콘서트 일정']
  const tabs = [['intro', labels[0]], ['albums', labels[1]], ['fans', 'FAN'], ['concerts', labels[2]]]
  return <section className="star-page">
    <nav className="star-tabs" aria-label="스타 정보 탭">{tabs.map(([key, label]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)} aria-selected={tab === key}>{label}{key === 'albums' && <b>{albumCatalog.length}</b>}{key === 'concerts' && <em>NEW</em>}</button>)}</nav>
    {tab === 'intro' && <article className="star-introduction"><div className="star-bio">{star.bio.map(paragraph => <p key={paragraph}>{paragraph}</p>)}</div><div className="star-records"><section><h3>HISTORY</h3><ul><li><time>2026</time> FAN HEAT 베스트 아티스트 선정</li><li><time>2024</time> 글로벌 팬 프로젝트 참여</li><li><time>{star.debut.slice(0, 4)}</time> 공식 데뷔</li></ul></section><section><h3>AWARD</h3><ul><li><time>2025</time> 올해의 아티스트</li><li><time>2024</time> 글로벌 팬 초이스</li><li><time>2023</time> 디지털 음원 본상</li></ul></section></div></article>}
    {tab === 'albums' && <StarAlbums star={star} />}
    {tab === 'fans' && <div className="star-fan-board"><h2>{star.name} 팬들의 이야기</h2>{['새로운 활동을 함께 기다리고 있어요!','오늘 무대도 정말 멋졌어요.','다음 앨범도 응원합니다.'].map((text, index) => <article key={text}><span>FH</span><div><strong>FANHEAT_{index + 1}</strong><p>{text}</p></div></article>)}</div>}
    {tab === 'concerts' && <div className="star-concerts"><h2>{star.name} 콘서트 일정</h2>{[['2026.09.12','SEOUL','KSPO DOME'],['2026.10.03','TOKYO','TOKYO DOME'],['2026.10.24','OSAKA','KYOCERA DOME']].map(([date, city, venue]) => <article key={date}><time>{date}</time><strong>{city}</strong><span>{venue}</span><button>일정 보기</button></article>)}</div>}
  </section>
}

function PostThumbnail({ images, title }) {
  const visibleImages = images.slice(0, 5)
  const [slide, setSlide] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [direction, setDirection] = useState('next')
  const dragStart = useRef(null)
  const suppressClick = useRef(false)
  useEffect(() => { if (slide >= visibleImages.length) setSlide(0) }, [slide, visibleImages.length])
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
        const next = distance < 0 ? (current + 1) % visibleImages.length : (current - 1 + visibleImages.length) % visibleImages.length
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
      if (visibleImages.length < 2) return
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
    <div className="post-media-viewport"><img key={`${visibleImages[slide]}-${slide}`} className={`post-media-current ${direction}`} src={assetSrc(visibleImages[slide])} alt={`${title} ${slide + 1}번째 이미지`} draggable="false" /></div>
    <div className="carousel-dots" aria-label={`${title} 이미지 선택`}>
      {visibleImages.map((_, index) => <button key={index} className={slide === index ? 'active' : ''} onClick={event => { event.stopPropagation(); moveTo(index, index >= slide ? 'next' : 'prev') }} aria-label={`${index + 1}번째 이미지`} />)}
    </div>
  </div>
}

function ImageLightbox({ images, initialIndex, title, onClose }) {
  const [index, setIndex] = useState(initialIndex)
  const [dragOffset, setDragOffset] = useState(0)
  const dragStart = useRef(null)
  const show = next => setIndex((next + images.length) % images.length)
  useEffect(() => {
    const onKeyDown = event => {
      if (event.key === 'Escape') onClose()
      if (event.key === 'ArrowLeft') setIndex(current => (current - 1 + images.length) % images.length)
      if (event.key === 'ArrowRight') setIndex(current => (current + 1) % images.length)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [images.length, onClose])
  const finishDrag = event => {
    if (dragStart.current === null) return
    const distance = event.clientX - dragStart.current
    if (Math.abs(distance) > 45) show(index + (distance < 0 ? 1 : -1))
    dragStart.current = null
    setDragOffset(0)
  }
  return <div className="image-lightbox" role="dialog" aria-modal="true" aria-label={`${title} 이미지 크게 보기`} onClick={onClose}>
    <div className="image-lightbox-panel" onClick={event => event.stopPropagation()}>
      <header><strong>{title}</strong><span>{index + 1} / {images.length}</span><button onClick={onClose} aria-label="이미지 팝업 닫기">×</button></header>
      <div className="image-lightbox-stage" onPointerDown={event => { dragStart.current = event.clientX; event.currentTarget.setPointerCapture(event.pointerId) }} onPointerMove={event => { if (dragStart.current !== null) setDragOffset(event.clientX - dragStart.current) }} onPointerUp={finishDrag} onPointerCancel={finishDrag}>
        <img src={assetSrc(images[index])} alt={`${title} ${index + 1}번째 큰 이미지`} draggable="false" style={{ transform: `translate3d(${dragOffset}px,0,0)` }} />
        {images.length > 1 && <><button className="image-lightbox-prev" onClick={() => show(index - 1)} aria-label="이전 큰 이미지">‹</button><button className="image-lightbox-next" onClick={() => show(index + 1)} aria-label="다음 큰 이미지">›</button></>}
      </div>
      {images.length > 1 && <div className="image-lightbox-thumbnails" aria-label="큰 이미지 선택">{images.map((image, imageIndex) => <button key={`${image}-${imageIndex}`} className={index === imageIndex ? 'active' : ''} onClick={() => setIndex(imageIndex)} aria-label={`${imageIndex + 1}번째 이미지 보기`}><img src={assetSrc(image)} alt="" /></button>)}</div>}
    </div>
  </div>
}

function HeatVote({ initialCount }) {
  const [count, setCount] = useState(initialCount)
  const [voted, setVoted] = useState(false)
  const tier = count >= 2000 ? 'viral' : count >= 1000 ? 'mint' : count >= 500 ? 'coral' : count >= 100 ? 'yellow' : 'soft'
  const toggleVote = event => {
    event.stopPropagation()
    setVoted(current => !current)
    setCount(current => current + (voted ? -1 : 1))
  }
  return <button className={`heat heat-${tier} ${voted ? 'voted' : ''}`} onClick={toggleVote} aria-pressed={voted} aria-label={`이 게시물에 보팅하기, 현재 ${count.toLocaleString()}명`}>
    <span className="heat-star-wrap" aria-hidden="true"><i className="heat-star" />{tier === 'viral' && <em className="heat-badge">HIT</em>}</span>
    <strong>{count.toLocaleString()}명</strong>
  </button>
}

function Feed({ query, onSelect, items = posts }) {
  const { locale, t, localizeTitle } = useI18n()
  const shown = items.filter(([title]) => title.toLowerCase().includes(query.toLowerCase()))
  return <section className="feed" id="feed">
    <div className="post-list">{shown.map(([title, image, data], index) => <article className="post" key={data?.id || `${title}-${index}`} onClick={() => onSelect({ title, image, index, data })} onKeyDown={event => event.key === 'Enter' && onSelect({ title, image, index, data })} tabIndex="0" aria-label={`${title} 상세 보기`}>
      <div className="post-index"><span>{index + 1}</span></div>
      <PostThumbnail images={shown[index][2]?.images?.length ? shown[index][2].images : postSlides[index] ?? [image]} title={localizeTitle(title)} />
      <div className="post-copy"><h3>{localizeTitle(title)}</h3><p>{locale === 'ko' ? shown[index][2]?.summary || t('defaultSummary') : t('defaultSummary')}</p><div className="stats post-meta"><span title="조회수"><i aria-hidden="true">◉</i>{(shown[index][2]?.view_count || 1200).toLocaleString()}</span><span title="선물"><i aria-hidden="true">♙</i>15</span><span title="댓글"><i aria-hidden="true">▱</i>{shown[index][2]?.comment_count || 3}</span><span className="post-meta-author" title="작성자"><i aria-hidden="true">♟</i>@{String(data?.author_display_name || 'FANHEAT').trim().replace(/\s+/g, '_')}</span></div></div>
      <HeatVote initialCount={shown[index][2]?.vote_count ?? voteCounts[index] ?? 20} />
    </article>)}</div>
    {!shown.length && <div className="empty">{t('empty')}</div>}
  </section>
}

function DetailAudioPlayer() {
  const audio = useRef(null)
  const [playing, setPlaying] = useState(false)
  const [muted, setMuted] = useState(false)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState(0)
  const format = value => `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, '0')}`
  const toggle = () => {
    if (playing) audio.current.pause()
    else audio.current.play()
    setPlaying(!playing)
  }
  const restart = () => {
    audio.current.currentTime = 0
    setProgress(0)
  }
  const toggleMute = () => {
    audio.current.muted = !muted
    setMuted(current => !current)
  }
  return <section className="detail-audio" aria-label="첨부 음원 플레이어">
    <audio ref={audio} src="/sample.mp3" onTimeUpdate={event => setProgress(event.currentTarget.currentTime)} onLoadedMetadata={event => setDuration(event.currentTarget.duration)} onEnded={() => setPlaying(false)} />
    <button className="audio-play" onClick={toggle} aria-label={playing ? '음원 일시정지' : '음원 재생'}>{playing ? 'Ⅱ' : '▶'}</button>
    <button className="audio-skip" onClick={restart} aria-label="처음으로">◀</button>
    <button className="audio-skip" onClick={restart} aria-label="다음 음원">▶</button>
    <button className="audio-volume" onClick={toggleMute} aria-label={muted ? '음소거 해제' : '음소거'}><img src={`${A}${muted ? 'volume_off.png' : 'volume_up.png'}`} alt="" /></button>
    <a className="audio-download" href="/sample.mp3" download aria-label="음원 다운로드">⬇</a>
    <img src={`${A}music1.jpg`} alt="" />
    <div className={`audio-info ${playing ? 'is-playing' : ''}`} style={{ '--audio-progress': `${duration ? Math.min(100, progress / duration * 100) : 0}%` }} role="progressbar" aria-label="음원 재생 위치" aria-valuemin="0" aria-valuemax={Math.floor(duration || 0)} aria-valuenow={Math.floor(progress)}><b>비도 오고 그래서</b><span>헤이즈 (Heize)</span></div>
    <time className="audio-time"><span>{format(progress)}</span><span>{format(duration)}</span></time>
    <button className="audio-menu" aria-label="재생목록">☰</button>
  </section>
}

function XPostEmbed({ postId, postUrl }) {
  return <section className="post-x-embed" aria-label="IVE 공식 X 게시물">
    <header><span className="x-brand" aria-hidden="true">𝕏</span><div><strong>IVE OFFICIAL</strong><small>@IVEstarship · 공식 X 게시물</small></div><a href={postUrl} target="_blank" rel="noreferrer">X에서 보기 ↗</a></header>
    <iframe src={`https://platform.twitter.com/embed/Tweet.html?id=${postId}&theme=light&dnt=true&lang=ko`} title="IVE 공식 X 최근 근황 게시물" loading="lazy" allowFullScreen />
    <p>X의 개인정보 설정이나 네트워크 환경에 따라 게시물이 표시되지 않을 수 있습니다. <a href={postUrl} target="_blank" rel="noreferrer">공식 게시물 열기</a></p>
  </section>
}

function FacebookPostEmbed({ postUrl }) {
  const embedUrl = `https://www.facebook.com/plugins/video.php?href=${encodeURIComponent(postUrl)}&show_text=true&width=500`
  return <section className="post-social-embed post-facebook-embed" aria-label="IVE 페이스북 게시물">
    <header><span className="social-brand" aria-hidden="true">f</span><div><strong>IVE OFFICIAL</strong><small>Facebook · 공식 영상 게시물</small></div><a href={postUrl} target="_blank" rel="noreferrer">Facebook에서 보기 ↗</a></header>
    <iframe src={embedUrl} title="IVE 공식 Facebook 영상 게시물" loading="lazy" allow="autoplay; clipboard-write; encrypted-media; picture-in-picture; web-share" allowFullScreen />
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

const commentFromRow = row => ({ id: row.id, authorId: row.author_id, parentId: row.parent_id, avatar: row.author_avatar_url, name: row.author_display_name, createdAt: row.created_at, updatedAt: row.updated_at, text: row.body, likes: Number(row.like_count || 0), dislikes: Number(row.dislike_count || 0) })

function Comments({ postId, user, onLogin, editCommentId }) {
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
    loadComments(postId).then(async rows => {
      if (!active) return
      setComments(rows.map(commentFromRow))
      const ownReactions = await loadCommentReactions(user?.id, rows.map(row => row.id))
      if (active) setReactions(new Map(ownReactions.map(row => [row.comment_id, row.reaction])))
    }).catch(cause => { if (active) setError(cause.message) })
    return () => { active = false }
  }, [postId, user?.id])
  useEffect(() => {
    if (!editCommentId) return
    const target = comments.find(comment => comment.id === editCommentId && comment.authorId === user?.id)
    if (!target) return
    setEditingId(target.id); setEditingValue(target.text)
    requestAnimationFrame(() => editingForm.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
  }, [comments, editCommentId, user?.id])
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
      setComments(current => current.filter(item => item.id !== comment.id && item.parentId !== comment.id))
    } catch (cause) { setError(cause.message) }
  }
  const roots = comments.filter(comment => !comment.parentId || !comments.some(parent => parent.id === comment.parentId))
  const repliesFor = id => comments.filter(comment => comment.parentId === id)
  const renderComment = (comment, depth = 0) => <article key={comment.id} className={depth ? 'comment-reply' : ''}>
    <div className="avatar">{comment.avatar ? <img src={assetSrc(comment.avatar)} alt={`${comment.name} 프로필`} /> : comment.name.split(' ').map(word => word[0]).join('').slice(0, 2)}</div>
    <div className="comment-main">{editingId === comment.id ? <form className="comment-edit-form" ref={editingForm} onSubmit={saveEdit}><strong>{comment.name}님의 댓글 수정</strong><textarea value={editingValue} onChange={event => setEditingValue(event.target.value)} maxLength="2000" autoFocus /><div><button type="button" onClick={() => setEditingId(null)}>취소</button><button type="submit" disabled={!editingValue.trim()}>수정 완료</button></div></form> : <>
      <header><strong>{comment.name}</strong><time>{relativeCommentTime(comment.createdAt)}{comment.updatedAt !== comment.createdAt ? ' · 수정됨' : ''}</time></header>
      <p>{comment.text}</p>
      <footer><span className="comment-reactions"><button className={`comment-reaction like ${reactions.get(comment.id) === 'like' ? 'active' : ''}`} onClick={() => toggleReaction(comment, 'like')} aria-label={`좋아요 ${comment.likes}건`} title="좋아요"><span aria-hidden="true">👍</span><b>{comment.likes.toLocaleString()}</b></button><button className={`comment-reaction dislike ${reactions.get(comment.id) === 'dislike' ? 'active' : ''}`} onClick={() => toggleReaction(comment, 'dislike')} aria-label={`싫어요 ${comment.dislikes}건`} title="싫어요"><span aria-hidden="true">👎</span><b>{comment.dislikes.toLocaleString()}</b></button></span><button className="comment-reply-button" onClick={() => { setReplyingId(replyingId === comment.id ? null : comment.id); setReplyValue('') }}>Reply</button>{comment.authorId === user?.id && <span className="comment-owner-actions"><button onClick={() => { setEditingId(comment.id); setEditingValue(comment.text) }}>Edit</button><button onClick={() => removeComment(comment)}>Delete</button></span>}</footer>
      {replyingId === comment.id && <form className="comment-reply-form" onSubmit={submitReply}><textarea value={replyValue} onChange={event => setReplyValue(event.target.value)} maxLength="2000" autoFocus placeholder={`${comment.name}님에게 답글 남기기`} /><div><button type="button" onClick={() => setReplyingId(null)}>취소</button><button type="submit" disabled={!replyValue.trim()}>답글 등록</button></div></form>}
    </>}</div>
    {depth === 0 && repliesFor(comment.id).length > 0 && <div className="comment-children">{repliesFor(comment.id).map(reply => renderComment(reply, 1))}</div>}
  </article>
  return <section className="comments">
    <div className="comment-heading"><h3>{t('comments')} {comments.length}</h3><span>{t('latest')}</span></div>
    <form className="comment-form" onSubmit={submit}>
      <textarea value={value} onChange={event => setValue(event.target.value)} maxLength="2000" placeholder={t('commentHint')} aria-label={t('comments')} />
      <div><span>{2000 - value.length}{t('charsLeft')}</span><button type="submit" disabled={!value.trim()}>{t('submitComment')}</button></div>
    </form>
    {error && <p className="form-error">{error}</p>}
    <div className="comment-list">{roots.map(comment => renderComment(comment))}</div>
  </section>
}

function PostDetail({ post, onClose, user, onLogin }) {
  const { localizeTitle } = useI18n()
  const [slide, setSlide] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [dragOffset, setDragOffset] = useState(0)
  const [lightboxIndex, setLightboxIndex] = useState(null)
  const [isScrolling, setIsScrolling] = useState(false)
  const dragStart = useRef(null)
  const suppressImageClick = useRef(false)
  const scrollHideTimer = useRef(null)
  const fallbackImages = postDetailFallbacks[post.index % postDetailFallbacks.length]
  const iveXPost = post.title === '오늘 공개된 무대 비하인드 모음' ? { id: '2034193103339589646', url: 'https://x.com/IVEstarship/status/2034193103339589646' } : null
  const iveFacebookPost = post.title === '컴백 쇼케이스에서 발견한 포인트' ? { url: 'https://www.facebook.com/100075906038750/videos/1804994100283626/' } : null
  const iveTikTokPost = post.title === '공항 출국길 패션 체크' ? { id: '7634017906199661845', url: 'https://www.tiktok.com/@ive.official/video/7634017906199661845' } : null
  const hasSocialEmbed = Boolean(iveXPost || iveFacebookPost || iveTikTokPost)
  const youtubeUrl = youtubeEmbedUrl(post.data?.reference_url)
  const hasInlineMedia = /<(img|iframe)\b|data-youtube-video/i.test(post.data?.body_html || '')
  const detailImages = hasInlineMedia || hasSocialEmbed ? [] : post.data?.images?.length ? post.data.images.slice(0, 5) : youtubeUrl ? [] : fallbackImages
  const finishDetailDrag = event => {
    if (dragStart.current === null) return
    const distance = event.clientX - dragStart.current
    if (Math.abs(distance) > 35) {
      suppressImageClick.current = true
      setSlide(current => distance < 0 ? Math.min(current + 1, detailImages.length - 1) : Math.max(current - 1, 0))
    }
    dragStart.current = null; setDragOffset(0); setDragging(false)
  }
  useEffect(() => () => window.clearTimeout(scrollHideTimer.current), [])
  const revealScrollbar = () => {
    setIsScrolling(true)
    window.clearTimeout(scrollHideTimer.current)
    scrollHideTimer.current = window.setTimeout(() => setIsScrolling(false), 850)
  }
  return <section className={`post-detail ${isScrolling ? 'is-scrolling' : ''}`} onScroll={revealScrollbar}>
    <div className="detail-hero">
      <div className="detail-meta"><time>2018-07-25 13:23:24</time><span><img src={`${A}gift_icon.png`} alt="선물" /><b>14명</b></span><span><img src={`${A}vote_icon2.png`} alt="업보트" /><b>$8.24</b></span></div>
      <h1>{localizeTitle(post.title)}</h1>
      <p>대한민국과 일본을 오가며 활발하게 활동하는 K-POP 아티스트의 새로운 소식입니다.</p>
    </div>
    <div className="detail-body">
      {iveXPost && <XPostEmbed postId={iveXPost.id} postUrl={iveXPost.url} />}
      {iveFacebookPost && <FacebookPostEmbed postUrl={iveFacebookPost.url} />}
      {iveTikTokPost && <TikTokPostEmbed videoId={iveTikTokPost.id} postUrl={iveTikTokPost.url} />}
      {detailImages.length > 0 && <div className={`detail-carousel ${dragging ? 'dragging' : ''}`} onPointerDown={event => { if (detailImages.length < 2) return; dragStart.current = event.clientX; setDragging(true); event.currentTarget.setPointerCapture(event.pointerId) }} onPointerMove={event => { if (dragStart.current !== null) setDragOffset(event.clientX - dragStart.current) }} onPointerUp={finishDetailDrag} onPointerCancel={finishDetailDrag}>
        <div className="detail-carousel-viewport"><div className="detail-carousel-track" style={{ transform: `translate3d(calc(-${slide * 100}% + ${dragOffset}px),0,0)` }}>{detailImages.map((image, index) => <img key={`${image}-${index}`} src={assetSrc(image)} alt={`${post.title} ${index + 1}번째 이미지`} draggable="false" onClick={() => { if (suppressImageClick.current) { suppressImageClick.current = false; return } setLightboxIndex(index) }} title="클릭하여 크게 보기" />)}</div></div>
        <button className="carousel-prev" onClick={() => setSlide((slide - 1 + detailImages.length) % detailImages.length)} aria-label="이전 이미지">‹</button>
        <button className="carousel-next" onClick={() => setSlide((slide + 1) % detailImages.length)} aria-label="다음 이미지">›</button>
        <div className="detail-carousel-dots">{detailImages.map((_, index) => <button key={index} className={slide === index ? 'active' : ''} onClick={() => setSlide(index)} aria-label={`${index + 1}번째 이미지`} />)}</div>
      </div>}
      {lightboxIndex !== null && <ImageLightbox images={detailImages} initialIndex={lightboxIndex} title={localizeTitle(post.title)} onClose={() => setLightboxIndex(null)} />}
      {youtubeUrl && <div className="post-youtube"><header><strong>YouTube</strong><span>첨부 영상</span></header><iframe src={youtubeUrl} title={`${post.title} YouTube 영상`} allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowFullScreen /></div>}
      <div className="detail-copy post-rich-content" dangerouslySetInnerHTML={{ __html: safeRichHtml(post.data?.body_html || '<p>오랜만에 글올쓰네요. 팬들과 함께 나누고 싶은 순간입니다.</p>') }} />
      <div className="detail-credits">
        <div className="detail-tags"><span>트와이스</span><span>서브보컬</span></div>
        <div className="author"><span>작성자 :</span><strong>@eye501</strong><em>Resteem</em></div>
      </div>
      <div className="reaction-buttons">
        <button className="reaction-gift"><img src={`${A}gift_icon2.png`} alt="" /><span>GIFT</span><b>14</b></button>
        <button className="reaction-upvote"><img src={`${A}vote_icon.png`} alt="" /><span>UPVOTE</span><b>$8.24</b></button>
      </div>
      <DetailAudioPlayer />
      <Comments postId={post.data?.id} user={user} onLogin={onLogin} editCommentId={post.editCommentId} />
    </div>
  </section>
}

const initialDraft = {
  title: '트와이스 사나',
  summary: '사나는 대한민국과 일본을 오가며 활발하게 활동하는 K-POP 아티스트입니다.',
  content: '오랜만에 글올쓰네요 트둥이사진으로 눈호강!!! 또 요즘 뜨 추워지니 원스여러분들 감기조심하세요~ 사나짱 모모짱♥♥♥',
  tags: '트와이스, 사나, 공항패션',
  reference: '',
}

const draftImageSrc = image => image.startsWith('blob:') || /^https?:\/\//.test(image) ? image : `${A}${image}`

function ComposerPreview({ draft }) {
  const tags = draft.tags.split(',').map(tag => tag.trim()).filter(Boolean)
  return <section className="post-detail compose-preview">
    <div className="detail-hero">
      <div className="detail-meta"><time>2018-07-25 13:23:24</time></div>
      <h1>{draft.title || '제목을 입력하세요'}</h1>
      <p>{draft.summary || '한줄 내용을 입력하면 여기에 미리 표시됩니다.'}</p>
    </div>
    <div className="detail-body">
      <div className="detail-copy preview-rich-text post-rich-content" dangerouslySetInnerHTML={{ __html: safeRichHtml(draft.content || '<p>본문 내용을 입력하세요.</p>') }} />
      <div className="detail-credits"><div className="detail-tags">{tags.map(tag => <span key={tag}>{tag}</span>)}</div><div className="author"><span>작성자 :</span><strong>@devdevil0625</strong><em>Preview</em></div></div>
      <div className="reaction-buttons"><button className="reaction-gift"><img src={`${A}gift_icon2.png`} alt="" /><span>GIFT</span><b>총 0명</b></button><button className="reaction-upvote"><img src={`${A}vote_icon.png`} alt="" /><span>UPVOTE</span><b>0명</b></button></div>
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
  return <div className="rich-editor tiptap-editor">
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
      <button type="button" className="editor-media-button" onClick={() => inlineImageInput.current?.click()} disabled={remainingImages < 1} aria-label="현재 위치에 이미지 삽입">▧ <span>이미지</span></button>
      <button type="button" className="editor-media-button" onClick={addYoutube} aria-label="현재 위치에 YouTube 삽입">▶ <span>YouTube</span></button>
      <input ref={inlineImageInput} hidden type="file" accept="image/*" multiple onChange={addInlineImages} />
      <button type="button" onClick={() => editor.chain().focus().undo().run()} disabled={!editor.can().chain().focus().undo().run()} aria-label="실행 취소">↶</button>
      <button type="button" onClick={() => editor.chain().focus().redo().run()} disabled={!editor.can().chain().focus().redo().run()} aria-label="다시 실행">↷</button>
    </div>
    <EditorContent editor={editor} />
    <small>{editor.getText().length}/1000</small>
  </div>
}

function WriteEditor({ draft, setDraft, images, setImages, imageFiles, setImageFiles, onClose, onPublish }) {
  const { t } = useI18n()
  const update = (key, value) => setDraft(current => ({ ...current, [key]: value }))
  const addInlineImages = (files, previews) => { setImages(current => [...current, ...previews].slice(0, 5)); setImageFiles(current => [...current, ...files].slice(0, 5)) }
  const music = [['music1.jpg', '비도 오고 그래서', '헤이즈 (Heize)'], ['music2.jpg', 'Siren', '선미'], ['music3.jpg', '몰랐니', "소녀시대-Oh!GG"]]
  return <section className="write-editor" aria-label="게시글 작성">
    <div className="write-editor-head"><div><h2>{t('newPost')}</h2><p>팬들과 나누고 싶은 순간을 자유롭게 기록해 보세요.</p></div><button onClick={onClose}>{t('close')}</button></div>
    <label className="write-field required"><span>{t('title')}</span><input value={draft.title} onChange={e => update('title', e.target.value)} /></label>
    <label className="write-field required"><span>{t('summary')}</span><div><input value={draft.summary} maxLength="60" onChange={e => update('summary', e.target.value)} /><small>{draft.summary.length}/60</small></div></label>
    <div className="write-field required editor-content-field"><span>{t('content')}</span><div><p className="editor-media-guide">본문을 작성하다가 원하는 위치에서 <b>이미지</b> 또는 <b>YouTube</b> 버튼을 눌러 콘텐츠 안에 바로 삽입하세요.</p><RichTextEditor value={draft.content} onChange={value => update('content', value)} onAddImages={addInlineImages} remainingImages={Math.max(0, 5 - imageFiles.length)} /></div></div>
    <label className="write-field required"><span>{t('tags')}</span><input value={draft.tags} onChange={e => update('tags', e.target.value)} /></label>
    <label className="write-field"><span>{t('reference')}</span><div className="link-input"><input value={draft.reference} onChange={e => update('reference', e.target.value)} placeholder="https://" /><button type="button">＋</button></div></label>
    <div className="write-field"><span>{t('addMusic')}</span><div><button className="music-search" type="button">▷ {t('musicSearch')}</button><div className="selected-music">{music.map(([image,title,artist], index) => <article key={title}><b>{String(index + 1).padStart(2,'0')}</b><img src={`${A}${image}`} alt="" /><span><strong>{title}</strong><small>{artist}</small></span><button type="button">×</button></article>)}</div></div></div>
    <div className="write-field"><span>{t('revenue')}</span><div className="revenue-box"><button type="button">♬ +</button><label><input value="@devdevil0625" readOnly /><input value="80%" readOnly /></label><label><input placeholder="@ ID" /><input placeholder="20%" /></label></div></div>
    <p className="write-guide"><b>※ 글 작성 이용안내</b><br />타인의 권리를 침해하지 않는 콘텐츠를 작성해 주세요. 본문 툴바에서 이미지는 최대 5장, YouTube 영상은 필요한 위치에 추가할 수 있습니다.</p>
    <button className="publish-button" type="button" onClick={onPublish}>{t('publish')}</button>
  </section>
}

function AuthModal({ onClose }) {
  const { t } = useI18n()
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
    const { error } = await supabase.auth.signInWithOAuth({ provider, options: { redirectTo: window.location.origin } })
    if (error) { setMessage(error.message); setPending(false) }
  }
  return <div className="auth-overlay" role="presentation" onMouseDown={event => event.target === event.currentTarget && onClose()}>
    <section className="auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-title">
      <button className="auth-close" onClick={onClose} aria-label="로그인 창 닫기">×</button>
      <div className="auth-brand"><img src={`${A}fanheat-logo.png`} alt="FAN HEAT" /><span>TURN UP THE HEAT</span></div>
      <div className="auth-content">
        <small>WELCOME TO FAN HEAT</small>
        <h2 id="auth-title">{mode === 'login' ? t('authTitle') : t('signupTitle')}</h2>
        <p>{mode === 'login' ? t('authDesc') : t('signupDesc')}</p>
        <form onSubmit={submit}>
          <label><span>{t('email')}</span><input type="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="fan@fanheat.com" required autoFocus /></label>
          <label><span>{t('password')}</span><input type="password" value={password} onChange={event => setPassword(event.target.value)} placeholder={t('passwordHint')} minLength="6" required /></label>
          <button className="email-auth" type="submit" disabled={pending}>{pending ? t('processing') : mode === 'login' ? t('emailLogin') : t('emailSignup')}</button>
        </form>
        {message && <p className="auth-message">{message}</p>}
        <div className="auth-divider"><span>{t('or')}</span></div>
        <button className="social-auth google" onClick={() => oauth('google')} disabled={pending}><img src={`${A}google-g.svg`} alt="" /> {t('google')}</button>
        <button className="social-auth kakao" onClick={() => oauth('kakao')} disabled={pending}><img src={`${A}kakao-talk.svg`} alt="" /> {t('kakao')}</button>
        <p className="auth-switch">{mode === 'login' ? t('noAccount') : t('haveAccount')} <button onClick={() => setMode(current => current === 'login' ? 'signup' : 'login')}>{mode === 'login' ? t('signup') : t('login')}</button></p>
        <p className="auth-terms">{t('terms')}</p>
      </div>
    </section>
  </div>
}

function Player({ songIndex, onClose, items = charts }) {
  const audio = useRef(null)
  const [playing, setPlaying] = useState(true)
  useEffect(() => { if (songIndex !== null) { audio.current.currentTime = 0; audio.current.play().then(() => setPlaying(true)).catch(() => setPlaying(false)) } }, [songIndex])
  if (songIndex === null) return <audio ref={audio} src="/sample.mp3" />
  const [title, artist, image] = items[songIndex]
  const toggle = () => { playing ? audio.current.pause() : audio.current.play(); setPlaying(!playing) }
  return <div className="player"><audio ref={audio} src="/sample.mp3" loop /><img src={assetSrc(image)} alt={`${title} 커버`} /><div><b>{title}</b><span>{artist}</span></div><button onClick={toggle} aria-label={playing ? '일시정지' : '재생'}>{playing ? 'Ⅱ' : '▶'}</button><button onClick={onClose} aria-label="플레이어 닫기">×</button></div>
}

function FanHeatApp() {
  const [query, setQuery] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const [songIndex, setSongIndex] = useState(null)
  const [chartCollapsed, setChartCollapsed] = useState(false)
  const [selectedPost, setSelectedPost] = useState(null)
  const [selectedStar, setSelectedStar] = useState(null)
  const [artistDirectory, setArtistDirectory] = useState(false)
  const [myPage, setMyPage] = useState(false)
  const [user, setUser] = useState(null)
  const [home, setHome] = useState({ tracks: charts, awards, posts, artists: [] })
  const [dataNotice, setDataNotice] = useState('')
  const [authOpen, setAuthOpen] = useState(false)
  const [writing, setWriting] = useState(false)
  const [draft, setDraft] = useState(initialDraft)
  const [draftImages, setDraftImages] = useState([])
  const [draftImageFiles, setDraftImageFiles] = useState([])
  const openWriter = () => { setSelectedPost(null); setSelectedStar(null); setArtistDirectory(false); setMyPage(false); setWriting(true) }
  const closeWriter = () => setWriting(false)
  const goHome = () => { setWriting(false); setSelectedPost(null); setSelectedStar(null); setArtistDirectory(false); setMyPage(false) }
  const openMyPage = () => { if (!user) { setAuthOpen(true); return }; setWriting(false); setSelectedPost(null); setSelectedStar(null); setMyPage(true) }
  const logout = async () => { await supabase?.auth.signOut(); goHome() }
  useEffect(() => {
    if (!supabase) { setDataNotice('Supabase 환경 변수를 확인해 주세요.'); return undefined }
    supabase.auth.getUser().then(({ data }) => setUser(data.user || null))
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => setUser(session?.user || null))
    loadHomeData().then(setHome).catch(error => setDataNotice(`DB 연결 실패: ${error.message}`))
    return () => listener.subscription.unsubscribe()
  }, [])
  const submitPost = async () => {
    if (!user) { setAuthOpen(true); return }
    try {
      await publishPost(draft, user, draftImageFiles, draftImages)
      setHome(await loadHomeData())
      setWriting(false)
    } catch (error) { setDataNotice(`글 저장 실패: ${error.message}`) }
  }
  return <div className="app" id="top">
    {writing
      ? <div className="detail-shell compose-shell"><ComposerPreview draft={draft} /></div>
      : selectedPost
      ? <div className="detail-shell"><PostDetail post={selectedPost} onClose={() => setSelectedPost(null)} user={user} onLogin={() => setAuthOpen(true)} /></div>
      : selectedStar
      ? <StarVisual star={selectedStar} onClose={goHome} />
      : myPage
      ? <MyPageProfile user={user} />
      : <div className={`left-shell ${chartCollapsed ? 'chart-collapsed' : ''}`} id="chart"><ChartPanel onPlay={setSongIndex} activeSong={songIndex} items={home.tracks} artists={home.artists} collapsed={chartCollapsed} onToggle={() => setChartCollapsed(value => !value)} user={user} onLogin={() => setAuthOpen(true)} /><Hero /></div>}
    <main className={`content ${writing ? 'writing-content' : ''} ${selectedStar ? 'star-content' : ''} ${myPage ? 'my-content' : ''} ${artistDirectory ? 'artist-directory-content' : ''}`}><Header {...{query, setQuery, menuOpen, setMenuOpen, writing, user}} loggedIn={Boolean(user)} onLogin={() => setAuthOpen(true)} onWrite={openWriter} onHome={goHome} onMyPage={openMyPage} onLogout={logout} />{dataNotice && <div className="data-notice">{dataNotice}</div>}{writing ? <WriteEditor draft={draft} setDraft={setDraft} images={draftImages} setImages={setDraftImages} imageFiles={draftImageFiles} setImageFiles={setDraftImageFiles} onClose={closeWriter} onPublish={submitPost} /> : selectedStar ? <StarPage star={selectedStar} /> : myPage ? <MyPageContent user={user} posts={home.posts} followers={home.awards} onSelect={post => { setMyPage(false); setSelectedPost(post) }} /> : artistDirectory ? <ArtistDirectory items={(home.artists.length ? home.artists.map((artist, index) => { const matched = home.awards.find(([name]) => name === (artist.name_ko || artist.name)); return [artist.name_ko || artist.name, matched?.[1] || 'FAN HEAT', artist.image_url || matched?.[2] || highResolutionFallbacks[index % highResolutionFallbacks.length], artist] }) : home.awards)} query={query} setQuery={setQuery} onClose={() => { setArtistDirectory(false); setQuery('') }} onSelect={star => { setArtistDirectory(false); setSelectedPost(null); setSelectedStar(star) }} /> : <><Awards items={home.awards} onViewAll={() => { setQuery(''); setArtistDirectory(true) }} onSelect={star => { setSelectedPost(null); setSelectedStar(star) }} /><Feed query={query} onSelect={setSelectedPost} items={home.posts} /></>}</main>
    {!writing && !selectedPost && !myPage && <Player songIndex={songIndex} onClose={() => setSongIndex(null)} items={home.tracks} />}
    {authOpen && <AuthModal onClose={() => setAuthOpen(false)} />}
  </div>
}

export default function App() {
  return <I18nProvider><FanHeatApp /></I18nProvider>
}
