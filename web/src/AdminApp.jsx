import { useEffect, useMemo, useState } from 'react'
import { supabase } from './lib/supabase'
import {
  isAdminUser,
  deleteAdminMembers,
  loadAdminAlbumDetail,
  loadAdminArtistDetail,
  loadAdminArtists,
  loadAdminComments,
  loadAdminDashboard,
  loadAdminFanPhotos,
  loadAdminMembers,
  loadAdminPosts,
  reviewAdminFanPhoto,
  updateAdminMember,
} from './lib/admin-api'
import { AlbumDetailPage, ArtistDetailPage, ArtistsPanel, CommentsPanel, PostsPanel } from './AdminContentPanels'

const ADMIN_ACCOUNT_EMAILS = {
  admin1: 'jh.park@illunex.com',
}

const sections = [
  ['dashboard', '/admin', '대시보드'],
  ['members', '/admin/members', '회원 관리'],
  ['artists', '/admin/artists', '아티스트 관리'],
  ['posts', '/admin/posts', '포스트 관리'],
  ['comments', '/admin/comments', '댓글 관리'],
  ['fan-photos', '/admin/fan-photos', '팬 사진 검토'],
]

const routeSection = path => sections.find(([, href]) => href !== '/admin' && path.startsWith(href))?.[0] || 'dashboard'
const artistRoute = path => {
  const matched = path.match(/^\/admin\/artists\/(\d+)(?:\/albums\/(\d+))?\/?$/)
  return { artistId: matched?.[1] ? Number(matched[1]) : null, albumId: matched?.[2] ? Number(matched[2]) : null }
}
const formatDate = value => value ? new Date(value).toLocaleString('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }) : '-'

function AdminLogin({ onAuthenticated }) {
  const [account, setAccount] = useState('admin1')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const submit = async event => {
    event.preventDefault()
    setBusy(true)
    setError('')
    const normalizedAccount = account.trim().toLowerCase()
    const email = ADMIN_ACCOUNT_EMAILS[normalizedAccount] || normalizedAccount
    const { data, error: signInError } = await supabase.auth.signInWithPassword({ email, password })
    if (signInError) setError('관리자 계정 또는 비밀번호를 확인해 주세요.')
    else {
      const { data: refreshed } = await supabase.auth.refreshSession()
      onAuthenticated(refreshed.user || data.user)
    }
    setBusy(false)
  }
  return <main className="admin-login-page"><div className="admin-login-card"><div className="admin-login-brand"><span>☆</span><strong>FAN HEAT</strong><small>CONTROL THE HEAT</small></div><form onSubmit={submit}><small>SECURE ADMIN ACCESS</small><h1>관리자 로그인</h1><p>회원과 아티스트 콘텐츠를 안전하게 관리합니다.</p><label>관리자 계정<input value={account} onChange={event => setAccount(event.target.value)} autoComplete="username" spellCheck="false" autoCapitalize="none" required autoFocus /></label><label>비밀번호<input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" required /></label>{error && <p className="admin-alert error">{error}</p>}<button disabled={busy}>{busy ? '확인 중…' : '로그인'}</button><small className="admin-login-help">등록된 관리자 계정만 접근할 수 있습니다.</small><a href="/">FANHEAT로 돌아가기</a></form></div></main>
}

function AccessDenied({ user, onLogout }) {
  return <main className="admin-login-page"><section className="admin-access-denied"><span>!</span><h1>관리자 권한이 없습니다</h1><p><b>{user.email}</b> 계정은 로그인되었지만 관리자 역할이 부여되지 않았습니다.</p><p>Supabase의 안전한 <code>app_metadata.role</code> 값이 <code>admin</code>인 계정만 접근할 수 있습니다.</p><div><button onClick={onLogout}>다른 계정으로 로그인</button><a href="/">FANHEAT 홈</a></div></section></main>
}

function Dashboard({ data }) {
  const metrics = [['MEMBERS', data.summary.members], ['ARTISTS', data.summary.artists], ['POSTS', data.summary.posts], ['COMMENTS', data.summary.comments], ['PHOTO REVIEW', data.summary.photos], ['TODAY VOTES', data.summary.votes]]
  return <><section className="admin-metrics">{metrics.map(([label, value]) => <article key={label}><span>{label}</span><strong>{Number(value || 0).toLocaleString()}</strong></article>)}</section><div className="admin-dashboard-grid"><section className="admin-panel"><header><h2>최근 포스트</h2></header>{data.recentPosts.map(post => <article className="admin-compact-row" key={post.id}><div><strong>{post.title}</strong><small>@{post.author_display_name}</small></div><span className={`admin-status ${post.status}`}>{post.status}</span></article>)}</section><section className="admin-panel"><header><h2>최근 댓글</h2></header>{data.recentComments.map(comment => <article className="admin-compact-row" key={comment.id}><div><strong>{comment.author_display_name}</strong><small>{comment.body}</small></div><time>{formatDate(comment.created_at)}</time></article>)}</section><section className="admin-panel audit-panel"><header><h2>관리자 감사 로그</h2></header>{data.auditLogs.map(log => <article className="admin-compact-row" key={log.id}><div><strong>{log.entity_type} · {log.action}</strong><small>{log.entity_id || '—'}</small></div><time>{formatDate(log.created_at)}</time></article>)}</section></div></>
}

function Members({ rows, onReload }) {
  const [editing, setEditing] = useState(null)
  const [tab, setTab] = useState('human')
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const [deleting, setDeleting] = useState(false)
  const humanCount = rows.filter(member => !member.is_ai).length
  const aiCount = rows.filter(member => member.is_ai).length
  const visibleRows = rows.filter(member => tab === 'ai' ? member.is_ai : !member.is_ai)
  const selectedCount = visibleRows.filter(member => selectedIds.has(member.id)).length
  const allSelected = visibleRows.length > 0 && selectedCount === visibleRows.length
  const save = async event => { event.preventDefault(); await updateAdminMember(editing.id, editing); setEditing(null); setSelectedIds(new Set()); onReload('회원 프로필을 저장했습니다.') }
  const changeTab = nextTab => { setTab(nextTab); setSelectedIds(new Set()) }
  const toggleSelected = id => setSelectedIds(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next })
  const toggleAll = () => setSelectedIds(allSelected ? new Set() : new Set(visibleRows.map(member => member.id)))
  const removeSelected = async () => {
    const ids = visibleRows.filter(member => selectedIds.has(member.id)).map(member => member.id)
    if (!ids.length || !window.confirm(`선택한 ${tab === 'ai' ? 'AI 회원' : '사람 회원'} ${ids.length}명을 삭제할까요? 회원 계정과 연결된 데이터가 함께 삭제되며 복구할 수 없습니다.`)) return
    setDeleting(true)
    try {
      const result = await deleteAdminMembers(ids)
      setSelectedIds(new Set())
      const failedCount = result?.failed?.length || 0
      await onReload(failedCount ? `${result.deleted.length}명을 삭제했고 ${failedCount}명은 보호 계정이거나 삭제에 실패했습니다.` : `선택한 회원 ${result.deleted.length}명을 삭제했습니다.`)
    } finally {
      setDeleting(false)
    }
  }
  return <><nav className="admin-member-tabs" aria-label="회원 유형"><button type="button" className={tab === 'human' ? 'active' : ''} onClick={() => changeTab('human')}>사람 회원 <span>{humanCount}</span></button><button type="button" className={tab === 'ai' ? 'active' : ''} onClick={() => changeTab('ai')}>AI 회원 <span>{aiCount}</span></button></nav><div className="admin-member-selection"><label><input type="checkbox" checked={allSelected} disabled={!visibleRows.length} onChange={toggleAll} /> 전체 선택</label><span>{selectedCount}명 선택</span><button type="button" disabled={!selectedCount || deleting} onClick={removeSelected}>{deleting ? '삭제 중…' : '선택 삭제'}</button></div><section className="admin-card-grid member-grid">{visibleRows.map(member => <article className={selectedIds.has(member.id) ? 'selected' : ''} key={member.id}><label className="admin-member-checkbox"><input type="checkbox" checked={selectedIds.has(member.id)} onChange={() => toggleSelected(member.id)} aria-label={`${member.display_name} 선택`} /></label><img src={member.avatar_url || '/images/icon_member.png'} alt="" /><span><strong>{member.display_name}{member.is_ai && <i className="admin-ai-badge">AI FAN</i>}</strong><small>{member.id}</small><em>{formatDate(member.created_at)} 가입</em></span><button type="button" onClick={() => setEditing({ ...member, avatar_url: member.avatar_url || '', bio: member.bio || '' })}>관리</button></article>)}{!visibleRows.length && <p className="admin-empty">검색 조건에 맞는 {tab === 'ai' ? 'AI 회원' : '사람 회원'}이 없습니다.</p>}</section>{editing && <div className="admin-modal-backdrop" onMouseDown={event => event.target === event.currentTarget && setEditing(null)}><form className="admin-modal" onSubmit={save}><header><div><small>MEMBER PROFILE</small><h2>{editing.display_name}</h2></div><button type="button" onClick={() => setEditing(null)}>×</button></header><label>표시 이름<input value={editing.display_name} onChange={event => setEditing({ ...editing, display_name: event.target.value })} required /></label><label>프로필 이미지 URL<input value={editing.avatar_url} onChange={event => setEditing({ ...editing, avatar_url: event.target.value })} /></label><label>소개<textarea value={editing.bio} onChange={event => setEditing({ ...editing, bio: event.target.value })} /></label><label className="admin-check"><input type="checkbox" checked={Boolean(editing.is_ai)} onChange={event => setEditing({ ...editing, is_ai: event.target.checked })} /> AI가 운영하는 팬 계정</label><button className="admin-primary">변경사항 저장</button></form></div>}</>
}

function FanPhotos({ rows, onReload }) {
  const [selected, setSelected] = useState(null)
  const [status, setStatus] = useState('pending')
  const [note, setNote] = useState('')
  const open = row => { setSelected(row); setStatus(row.status); setNote(row.admin_note || '') }
  const save = async event => { event.preventDefault(); await reviewAdminFanPhoto(selected.id, status, note); setSelected(null); onReload('팬 사진 검토 결과를 저장했습니다.') }
  return <><section className="admin-photo-grid">{rows.map(row => <button type="button" key={row.id} onClick={() => open(row)}><div>{row.images[0]?.signed_url ? <img src={row.images[0].signed_url} alt="" /> : <span>사진 없음</span>}</div><article><small className={`admin-status ${row.status}`}>{row.status}</small><h2>@{row.submitter_name}</h2><p>{row.note || '사진 설명이 없습니다.'}</p><footer>{row.images.length}장 · {formatDate(row.created_at)}</footer></article></button>)}</section>{selected && <div className="admin-modal-backdrop" onMouseDown={event => event.target === event.currentTarget && setSelected(null)}><form className="admin-modal photo-review-modal" onSubmit={save}><header><div><small>FAN PHOTO REVIEW</small><h2>@{selected.submitter_name}</h2></div><button type="button" onClick={() => setSelected(null)}>×</button></header><div className="admin-review-images">{selected.images.map(image => <figure key={image.id}><img src={image.signed_url} alt={image.original_filename} /><figcaption>{image.width}×{image.height}</figcaption></figure>)}</div><p>{selected.note || '사진 설명이 없습니다.'}</p><label>검토 상태<select value={status} onChange={event => setStatus(event.target.value)}><option value="pending">검토 대기</option><option value="approved">배경 사용 승인</option><option value="rejected">반려</option></select></label><label>관리자 메모<textarea value={note} onChange={event => setNote(event.target.value)} /></label><button className="admin-primary">검토 결과 저장</button></form></div>}</>
}

export default function AdminApp() {
  const [user, setUser] = useState(undefined)
  const [section] = useState(() => routeSection(window.location.pathname))
  const [{ artistId, albumId }] = useState(() => artistRoute(window.location.pathname))
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [memberQuery, setMemberQuery] = useState('')
  useEffect(() => {
    if (!supabase) { setError('Supabase 환경 변수가 설정되지 않았습니다.'); setUser(null); return }
    supabase.auth.refreshSession().then(async ({ data: refreshed }) => {
      if (refreshed.user) setUser(refreshed.user)
      else {
        const { data: auth } = await supabase.auth.getUser()
        setUser(auth.user || null)
      }
    })
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => setUser(session?.user || null))
    return () => listener.subscription.unsubscribe()
  }, [])
  const load = async message => {
    if (!isAdminUser(user)) return
    setBusy(true); setError(''); if (message) setNotice(message)
    try {
      const next = section === 'dashboard' ? await loadAdminDashboard() : section === 'members' ? await loadAdminMembers(memberQuery) : section === 'artists' ? albumId ? await loadAdminAlbumDetail(albumId) : artistId ? await loadAdminArtistDetail(artistId) : await loadAdminArtists() : section === 'posts' ? await Promise.all([loadAdminPosts(), loadAdminArtists()]).then(([posts, artists]) => ({ posts, artists })) : section === 'comments' ? await loadAdminComments() : await loadAdminFanPhotos()
      setData(next)
    } catch (loadError) { setError(loadError.message) }
    finally { setBusy(false) }
  }
  useEffect(() => { load() }, [user, section])
  const title = useMemo(() => albumId ? '앨범 상세 관리' : artistId ? '아티스트 상세 관리' : sections.find(([key]) => key === section)?.[2] || '관리자', [section, artistId, albumId])
  const logout = async () => { await supabase.auth.signOut(); setUser(null) }
  if (user === undefined) return <main className="admin-loading">관리자 세션을 확인하고 있습니다…</main>
  if (!user) return <AdminLogin onAuthenticated={setUser} />
  if (!isAdminUser(user)) return <AccessDenied user={user} onLogout={logout} />
  return <div className="admin-app"><aside className="admin-sidebar"><a className="admin-brand" href="/admin"><span>☆</span><strong>FAN HEAT</strong><small>ADMIN CONSOLE</small></a><nav>{sections.map(([key, href, label]) => <a className={section === key ? 'active' : ''} href={href} key={key}>{label}</a>)}</nav><div><a href="/">사용자 페이지</a><button onClick={logout}>로그아웃</button></div></aside><main className="admin-main"><header className="admin-topbar"><div><small>FANHEAT BACK OFFICE</small><h1>{title}</h1></div><span>{user.email}</span></header><section className="admin-content">{notice && <p className="admin-alert">{notice}</p>}{error && <p className="admin-alert error">{error}</p>}{section === 'members' && <form className="admin-search" onSubmit={event => { event.preventDefault(); load() }}><input value={memberQuery} onChange={event => setMemberQuery(event.target.value)} placeholder="회원 이름 또는 ID 검색" /><button>검색</button></form>}{busy && !data ? <p className="admin-loading">데이터를 불러오고 있습니다…</p> : data && (section === 'dashboard' ? <Dashboard data={data} /> : section === 'members' ? <Members rows={data} onReload={load} /> : section === 'artists' ? albumId ? <AlbumDetailPage initial={data} onChanged={load} /> : artistId ? <ArtistDetailPage initial={data} onChanged={load} /> : <ArtistsPanel rows={data} onReload={load} /> : section === 'posts' ? <PostsPanel rows={data.posts} artists={data.artists} onReload={load} /> : section === 'comments' ? <CommentsPanel rows={data} onReload={load} /> : <FanPhotos rows={data} onReload={load} />)}</section></main></div>
}
