import { setAdminAlbumVisibility, setAdminGalleryReview } from './lib/admin-api'
import AdminArtistImages from './AdminArtistImages'
import { artistStatus, artistStatusLabels, pendingCorrectionCount, filterAdminArtists } from './lib/admin-artist-list'
import AdminCorrectionRequests from './AdminCorrectionRequests'
import AdminGallerySource from './AdminGallerySource'
import { useEffect, useMemo, useState } from 'react'
import AdminTimelineEditor, { timelineDraft, timelineValues } from './AdminTimelineEditor'
import {
  deleteAdminArtistRelation,
  deleteAdminArtistRelations,
  deleteAdminAlbumTrack,
  deleteAdminPosts,
  hideAdminComment,
  loadAdminAlbumDetail,
  loadAdminArtistDetail,
  loadAdminPostDetail,
  saveAdminAlbumTrack,
  saveAdminArtistRelation,
  updateAdminArtist,
  setAdminArtistVisibility,
  updateAdminComment,
  updateAdminPost,
} from './lib/admin-api'

const formatDate = value => value ? new Date(value).toLocaleString('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }) : '-'
const safeLower = value => String(value || '').toLocaleLowerCase('ko-KR')
const parseLines = value => String(value || '').split('\n').map(item => item.trim()).filter(Boolean)
const galleryDecisionLabels = { photo_candidate: '활동 사진 후보', review: 'AI 확인 보류', exclude: 'AI 제외 권고' }
const galleryReviewLabels = { pending: '확인 필요', approved: '승인됨', rejected: '제외됨' }

const relationConfig = {
  albums: {
    table: 'artist_albums', title: '앨범', rows: 'artist_albums',
    empty: { title: '', lead_track: '', release_date: '', album_type: '앨범', track_count: 1, cover_url: '', youtube_url: '', description: '', label: '', genre: '', external_url: '', active: true, display_order: 0 },
    summary: item => `${item.release_date || '발매일 미정'} · ${item.album_type} · 수록곡 ${item.artist_album_tracks?.length ?? 0}곡 · YouTube 연결 ${(item.artist_album_tracks || []).filter(track => track.youtube_url?.trim()).length}곡`,
  },
  fans: {
    table: 'artist_fans', title: '팬', rows: 'artist_fans',
    empty: { display_name: '', handle: '@', avatar_url: '', heat_percent: 0, featured_rank: '', active: true, display_order: 0 },
    summary: item => `${item.handle} · HEAT ${item.heat_percent}%${item.featured_rank ? ` · ${item.featured_rank}위` : ''}`,
  },
  gallery: {
    table: 'artist_gallery_items', title: '갤러리', rows: 'artist_gallery_items',
    empty: { title: '', image_url: '', source_page_url: '', original_image_url: '', source_provider: '', creator_name: '', license_name: '', license_url: '', attribution_text: '', captured_on: '', active: true, display_order: 0 },
    summary: item => item.captured_on || '날짜 미정',
  },
}

function RelationFields({ type, value, setValue }) {
  const update = (key, next) => setValue(current => ({ ...current, [key]: next }))
  if (type === 'albums') return <><div className="admin-form-columns admin-relation-fields"><label>앨범명<input value={value.title} onChange={event => update('title', event.target.value)} required /></label><label>대표곡<input value={value.lead_track} onChange={event => update('lead_track', event.target.value)} /></label><label>발매일<input type="date" value={value.release_date || ''} onChange={event => update('release_date', event.target.value)} /></label><label>앨범 유형<input value={value.album_type} onChange={event => update('album_type', event.target.value)} /></label><label>레이블<input value={value.label || ''} onChange={event => update('label', event.target.value)} /></label><label>장르<input value={value.genre || ''} onChange={event => update('genre', event.target.value)} /></label><label>수록곡 수<input type="number" min="0" max="200" value={value.track_count} onChange={event => update('track_count', event.target.value)} /></label><label>표시 순서<input type="number" value={value.display_order} onChange={event => update('display_order', event.target.value)} /></label><label>커버 이미지 URL<input value={value.cover_url || ''} onChange={event => update('cover_url', event.target.value)} /></label><label>YouTube URL<input value={value.youtube_url || ''} onChange={event => update('youtube_url', event.target.value)} /></label><label>외부 상세 URL<input value={value.external_url || ''} onChange={event => update('external_url', event.target.value)} /></label></div><label>앨범 소개<textarea value={value.description || ''} onChange={event => update('description', event.target.value)} /></label></>
  if (type === 'fans') return <div className="admin-form-columns admin-relation-fields"><label>표시 이름<input value={value.display_name} onChange={event => update('display_name', event.target.value)} required /></label><label>팬 ID<input value={value.handle} onChange={event => update('handle', event.target.value)} required /></label><label>프로필 이미지 URL<input value={value.avatar_url || ''} onChange={event => update('avatar_url', event.target.value)} /></label><label>HEAT<input type="number" min="0" max="100" value={value.heat_percent} onChange={event => update('heat_percent', event.target.value)} /></label><label>대표 팬 순위<input type="number" min="1" value={value.featured_rank || ''} onChange={event => update('featured_rank', event.target.value)} placeholder="일반 팬은 비워두기" /></label><label>표시 순서<input type="number" value={value.display_order} onChange={event => update('display_order', event.target.value)} /></label></div>
  return <div className="admin-form-columns admin-relation-fields"><label>갤러리 제목<input value={value.title} onChange={event => update('title', event.target.value)} required /></label><label>촬영·게시일<input type="date" value={value.captured_on || ''} onChange={event => update('captured_on', event.target.value)} /></label><label>이미지 URL<input value={value.image_url} onChange={event => update('image_url', event.target.value)} required /></label><label>출처 페이지 URL<input type="url" value={value.source_page_url || ''} onChange={event => update('source_page_url', event.target.value)} placeholder="이미지가 게시된 원래 페이지" /></label><label>원본 이미지 URL<input type="url" value={value.original_image_url || ''} onChange={event => update('original_image_url', event.target.value)} placeholder="수집 당시 이미지 파일 주소" /></label><label>제공처<input value={value.source_provider || ''} onChange={event => update('source_provider', event.target.value)} placeholder="예: wikimedia_commons" /></label><label>촬영자·저작자<input value={value.creator_name || ''} onChange={event => update('creator_name', event.target.value)} /></label><label>라이선스<input value={value.license_name || ''} onChange={event => update('license_name', event.target.value)} placeholder="예: CC BY-SA 4.0" /></label><label>라이선스 URL<input type="url" value={value.license_url || ''} onChange={event => update('license_url', event.target.value)} /></label><label>표시 순서<input type="number" value={value.display_order} onChange={event => update('display_order', event.target.value)} /></label><label className="admin-form-wide">권리 표기 문구<input value={value.attribution_text || ''} onChange={event => update('attribution_text', event.target.value)} placeholder="촬영자 · 라이선스 · 제공처" /></label></div>
}

function ArtistRelations({ artist, type, onRefresh }) {
  const [visibilityBusy, setVisibilityBusy] = useState(false)
  const [visibilityError, setVisibilityError] = useState('')
  const [includeTracks, setIncludeTracks] = useState(true)
  const [galleryReviewBusy, setGalleryReviewBusy] = useState(false)
  const [galleryReviewError, setGalleryReviewError] = useState('')
  const [galleryReviewFilter, setGalleryReviewFilter] = useState('all')
  const [galleryLicenseFilter, setGalleryLicenseFilter] = useState('all')
  const [galleryProviderFilter, setGalleryProviderFilter] = useState('all')
  const changeVisibility = async (ids, active) => {
    if (visibilityBusy || !ids.length) return
    if (!window.confirm(`앨범 ${ids.length}개를 ${active ? '공개' : '비공개'}로 변경할까요?\n${includeTracks ? '해당 앨범의 모든 수록곡도 함께 변경됩니다.' : '수록곡의 개별 공개 설정은 유지됩니다.'}\n아티스트가 비공개이면 사용자 화면에는 노출되지 않습니다.`)) return
    setVisibilityBusy(true); setVisibilityError('')
    try { await setAdminAlbumVisibility(artist.id, ids, active, includeTracks); setEditing(null); await onRefresh('앨범 공개 설정을 저장했습니다.'); setSelectedIds(new Set()) }
    catch (error) { setVisibilityError(error.message || '공개 설정을 저장하지 못했습니다.') }
    finally { setVisibilityBusy(false) }
  }
  const config = relationConfig[type]
  const [editing, setEditing] = useState(null)
  const [previewing, setPreviewing] = useState(null)
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const [deletingSelected, setDeletingSelected] = useState(false)
  const allRows = [...(artist[config.rows] || [])].sort((a, b) => {
    if (type === 'gallery') {
      const reviewOrder = { pending: 0, approved: 1, rejected: 2 }
      const statusDelta = (reviewOrder[a.review_status] ?? 3) - (reviewOrder[b.review_status] ?? 3)
      if (statusDelta) return statusDelta
    }
    return Number(a.display_order || 0) - Number(b.display_order || 0)
  })
  const galleryLicenseOptions = type === 'gallery' ? [...new Set(allRows.map(item => String(item.license_name || '').trim() || '__missing__'))].sort((a, b) => a === '__missing__' ? 1 : b === '__missing__' ? -1 : a.localeCompare(b, 'ko')) : []
  const galleryProviderOptions = type === 'gallery' ? [...new Set(allRows.map(item => String(item.source_provider || '').trim() || '__missing__'))].sort((a, b) => a === '__missing__' ? 1 : b === '__missing__' ? -1 : a.localeCompare(b, 'ko')) : []
  const rows = type === 'gallery' ? allRows.filter(item => {
    const reviewStatus = item.review_status || (item.active ? 'approved' : 'pending')
    const license = String(item.license_name || '').trim() || '__missing__'
    const provider = String(item.source_provider || '').trim() || '__missing__'
    return (galleryReviewFilter === 'all' || reviewStatus === galleryReviewFilter)
      && (galleryLicenseFilter === 'all' || license === galleryLicenseFilter)
      && (galleryProviderFilter === 'all' || provider === galleryProviderFilter)
  }) : allRows
  const galleryCandidates = type === 'gallery' ? allRows.filter(item => item.ai_decision) : []
  const pendingGalleryCount = galleryCandidates.filter(item => item.review_status === 'pending').length
  const selectedCount = rows.filter(item => selectedIds.has(item.id)).length
  const allSelected = rows.length > 0 && selectedCount === rows.length
  const save = async event => { event.preventDefault(); await saveAdminArtistRelation(config.table, artist.id, editing); setEditing(null); await onRefresh(`${config.title} 정보를 저장했습니다.`) }
  const remove = async item => { if (!window.confirm(`${item.title || item.display_name} 항목을 삭제할까요?`)) return; await deleteAdminArtistRelation(config.table, item.id); await onRefresh(`${config.title} 항목을 삭제했습니다.`) }
  const toggleSelected = id => setSelectedIds(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next })
  const toggleAll = () => setSelectedIds(allSelected ? new Set() : new Set(rows.map(item => item.id)))
  const removeSelected = async () => {
    const ids = rows.filter(item => selectedIds.has(item.id)).map(item => item.id)
    if (!ids.length || !window.confirm(`선택한 ${config.title} ${ids.length}개를 삭제할까요? 삭제한 항목은 복구할 수 없습니다.`)) return
    setDeletingSelected(true)
    try {
      await deleteAdminArtistRelations(config.table, ids)
      setSelectedIds(new Set())
      await onRefresh(`선택한 ${config.title} ${ids.length}개를 삭제했습니다.`)
    } finally {
      setDeletingSelected(false)
    }
  }
  const reviewGallery = async (items, reviewStatus) => {
    const ids = items.filter(item => item.review_status === 'pending').map(item => item.id)
    if (!ids.length || galleryReviewBusy) return
    const approving = reviewStatus === 'approved'
    if (!window.confirm(approving
      ? `선택한 이미지 후보 ${ids.length}개를 승인해 사용자 갤러리에 공개할까요?\n이미지와 출처·이용 권리를 확인한 뒤 진행해 주세요.`
      : `선택한 이미지 후보 ${ids.length}개를 제외할까요?\n이미지는 사용자 페이지에 공개되지 않고 검토 기록은 유지됩니다.`)) return
    setGalleryReviewBusy(true); setGalleryReviewError('')
    try {
      await setAdminGalleryReview(artist.id, ids, reviewStatus)
      setSelectedIds(new Set())
      await onRefresh(approving ? `이미지 후보 ${ids.length}개를 승인했습니다.` : `이미지 후보 ${ids.length}개를 제외했습니다.`)
    } catch (error) {
      setGalleryReviewError(error.message || '갤러리 검토 결과를 저장하지 못했습니다.')
    } finally {
      setGalleryReviewBusy(false)
    }
  }
  useEffect(() => {
    setSelectedIds(new Set())
    setEditing(null)
    setPreviewing(null)
    setGalleryReviewFilter('all')
    setGalleryLicenseFilter('all')
    setGalleryProviderFilter('all')
  }, [type, artist.id])
  useEffect(() => {
    setSelectedIds(new Set())
    setPreviewing(null)
  }, [galleryReviewFilter, galleryLicenseFilter, galleryProviderFilter])
  const previewIndex = previewing ? rows.findIndex(item => item.id === previewing.id) : -1
  const showAdjacentPreview = direction => setPreviewing(current => {
    if (!current || rows.length < 2) return current
    const currentIndex = rows.findIndex(item => item.id === current.id)
    return rows[(currentIndex + direction + rows.length) % rows.length]
  })
  useEffect(() => {
    if (!previewing) return undefined
    const navigatePreview = event => {
      if (event.key === 'Escape') setPreviewing(null)
      if (event.key === 'ArrowLeft') showAdjacentPreview(-1)
      if (event.key === 'ArrowRight') showAdjacentPreview(1)
    }
    document.addEventListener('keydown', navigatePreview)
    return () => document.removeEventListener('keydown', navigatePreview)
  }, [previewing?.id, rows.length])
  return <section className="admin-detail-section">
    <header><div><small>ARTIST {type.toUpperCase()}</small><h3>{config.title} 관리</h3></div><button type="button" className="admin-add-button" onClick={() => setEditing({ ...config.empty })}>＋ {config.title} 추가</button></header>
    {type === 'albums' && <div className="admin-album-visibility"><label><input type="checkbox" checked={includeTracks} onChange={e => setIncludeTracks(e.target.checked)} /> 수록곡도 함께 공개·비공개 변경</label><p>체크하지 않으면 앨범만 변경됩니다. 비공개 수록곡과 연결 영상은 사용자에게 표시되지 않습니다.</p>{visibilityError && <p role="alert">{visibilityError}</p>}</div>}
    {type === 'gallery' && galleryCandidates.length > 0 && <div className="admin-gallery-review-summary">
      <div><strong>AI 이미지 후보 검토</strong><p>판별된 모든 이미지를 확인한 뒤 승인하거나 제외해 주세요. 승인 전에는 사용자 페이지에 표시되지 않습니다.</p></div>
      <dl><div><dt>확인 필요</dt><dd>{pendingGalleryCount}</dd></div><div><dt>승인</dt><dd>{galleryCandidates.filter(item => item.review_status === 'approved').length}</dd></div><div><dt>제외</dt><dd>{galleryCandidates.filter(item => item.review_status === 'rejected').length}</dd></div></dl>
    </div>}
    {type === 'gallery' && allRows.length > 0 && <div className="admin-gallery-filters" aria-label="갤러리 필터">
      <label><span>검토 상태</span><select value={galleryReviewFilter} onChange={event => setGalleryReviewFilter(event.target.value)}><option value="all">전체 상태</option><option value="pending">확인 필요</option><option value="approved">승인됨</option><option value="rejected">제외됨</option></select></label>
      <label><span>라이선스 조건</span><select value={galleryLicenseFilter} onChange={event => setGalleryLicenseFilter(event.target.value)}><option value="all">전체 라이선스</option>{galleryLicenseOptions.map(value => <option value={value} key={value}>{value === '__missing__' ? '미기록' : value}</option>)}</select></label>
      <label><span>제공처</span><select value={galleryProviderFilter} onChange={event => setGalleryProviderFilter(event.target.value)}><option value="all">전체 제공처</option>{galleryProviderOptions.map(value => <option value={value} key={value}>{value === '__missing__' ? '미기록' : value}</option>)}</select></label>
      <div><strong>{rows.length.toLocaleString()}개</strong><span>/ 전체 {allRows.length.toLocaleString()}개</span><button type="button" disabled={galleryReviewFilter === 'all' && galleryLicenseFilter === 'all' && galleryProviderFilter === 'all'} onClick={() => { setGalleryReviewFilter('all'); setGalleryLicenseFilter('all'); setGalleryProviderFilter('all') }}>필터 초기화</button></div>
    </div>}
    {galleryReviewError && <p className="admin-gallery-review-error" role="alert">{galleryReviewError}</p>}
    {rows.length > 0 && <div className="admin-relation-selection"><label><input type="checkbox" checked={allSelected} onChange={toggleAll} /> 전체 선택</label><span>{selectedCount}개 선택</span>
      {type === 'albums' && <><button type="button" disabled={!selectedCount || visibilityBusy || deletingSelected} onClick={() => changeVisibility(rows.filter(r => selectedIds.has(r.id)).map(r => r.id), true)}>선택 공개</button><button type="button" disabled={!selectedCount || visibilityBusy || deletingSelected} onClick={() => changeVisibility(rows.filter(r => selectedIds.has(r.id)).map(r => r.id), false)}>선택 비공개</button></>}
      {type === 'gallery' && <><button type="button" disabled={galleryReviewBusy || !rows.some(item => selectedIds.has(item.id) && item.review_status === 'pending')} onClick={() => reviewGallery(rows.filter(item => selectedIds.has(item.id)), 'approved')}>선택 승인</button><button type="button" disabled={galleryReviewBusy || !rows.some(item => selectedIds.has(item.id) && item.review_status === 'pending')} onClick={() => reviewGallery(rows.filter(item => selectedIds.has(item.id)), 'rejected')}>선택 제외</button></>}
      <button type="button" disabled={!selectedCount || deletingSelected || galleryReviewBusy} onClick={removeSelected}>{deletingSelected ? '삭제 중…' : '선택 삭제'}</button>
    </div>}
    <div className="admin-relation-list">{rows.map(item => <article className={`admin-relation-item ${type} review-${item.review_status || 'manual'} ${selectedIds.has(item.id) ? 'selected' : ''}`} key={item.id}>
      <label className="admin-relation-checkbox"><input type="checkbox" checked={selectedIds.has(item.id)} onChange={() => toggleSelected(item.id)} aria-label={`${item.title || item.display_name} 선택`} /></label>
      {type === 'gallery' ? <button type="button" className="admin-gallery-preview-trigger" onClick={() => setPreviewing(item)} aria-label={`${item.title} 이미지 크게 보기`}><img src={item.image_url || '/images/icon_member.png'} alt="" /><span>미리보기</span></button> : type !== 'fans' && <img src={item.cover_url || '/images/icon_member.png'} alt="" />}
      <div><strong>{item.title || item.display_name}</strong><span>{config.summary(item)}</span><small>{item.active ? '사용자 페이지 공개' : '비공개'} · 순서 {item.display_order}</small>
        {type === 'gallery' && item.ai_decision && <div className="admin-gallery-ai-review"><span className={`status-${item.review_status || 'pending'}`}>{galleryReviewLabels[item.review_status] || '확인 필요'}</span><b>{galleryDecisionLabels[item.ai_decision] || item.ai_decision}</b>{item.ai_confidence != null && <small>신뢰도 {Math.round(Number(item.ai_confidence) * 100)}%</small>}{item.ai_category && <small>분류 {item.ai_category}</small>}{item.ai_reason && <p>{item.ai_reason}</p>}</div>}
        {type === 'gallery' && <AdminGallerySource item={item} />}
      </div>
      {type === 'albums' && <button type="button" disabled={visibilityBusy || deletingSelected} onClick={() => changeVisibility([item.id], !item.active)}>{item.active ? '비공개로 변경' : '공개로 변경'}</button>}
      {type === 'albums' && <a className="admin-relation-detail" href={`/admin/artists/${artist.id}/albums/${item.id}`}>상세·수록곡</a>}
      {type === 'gallery' ? <div className="admin-gallery-review-actions">{item.review_status === 'pending' && <><button type="button" disabled={galleryReviewBusy} onClick={() => reviewGallery([item], 'approved')}>승인</button><button type="button" className="reject" disabled={galleryReviewBusy} onClick={() => reviewGallery([item], 'rejected')}>제외</button></>}<button type="button" onClick={() => setEditing({ ...config.empty, ...item })}>수정</button><button type="button" className="danger" onClick={() => remove(item)}>삭제</button></div> : <><button type="button" onClick={() => setEditing({ ...config.empty, ...item })}>수정</button>{type !== 'albums' && <button type="button" className="danger" onClick={() => remove(item)}>삭제</button>}</>}
    </article>)}{!rows.length && <p className="admin-empty">{type === 'gallery' && allRows.length ? '선택한 필터에 해당하는 갤러리 이미지가 없습니다.' : `Supabase에 등록된 ${config.title} 정보가 없습니다.`}</p>}</div>
    {editing && <form className="admin-inline-editor" onSubmit={save}><header><strong>{editing.id ? `${config.title} 수정` : `${config.title} 추가`}</strong><button type="button" onClick={() => setEditing(null)}>×</button></header><RelationFields type={type} value={editing} setValue={setEditing} />{type === 'gallery' && editing.ai_decision ? <p className="admin-gallery-edit-review-note">AI 수집 후보의 공개 여부는 목록의 승인·제외 버튼으로 변경해 주세요.</p> : <label className="admin-check"><input type="checkbox" checked={editing.active} onChange={event => setEditing({ ...editing, active: event.target.checked })} /> 사용자 페이지에 공개</label>}<button className="admin-primary">저장</button></form>}
    {previewing && <div className="admin-gallery-preview-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setPreviewing(null) }}><section className="admin-gallery-preview" role="dialog" aria-modal="true" aria-labelledby="admin-gallery-preview-title"><header><div><small>GALLERY PREVIEW <b>{previewIndex + 1} / {rows.length}</b></small><h3 id="admin-gallery-preview-title">{previewing.title}</h3><p>{previewing.captured_on || '날짜 미정'} · {galleryReviewLabels[previewing.review_status] || (previewing.active ? '사용자 페이지 공개' : '비공개')} · 순서 {previewing.display_order}</p>{previewing.ai_reason && <p className="admin-gallery-preview-reason">{galleryDecisionLabels[previewing.ai_decision]} · {previewing.ai_reason}</p>}</div><button type="button" onClick={() => setPreviewing(null)} aria-label="미리보기 닫기">×</button></header><AdminGallerySource item={previewing} /><div className="admin-gallery-preview-canvas">{rows.length > 1 && <button type="button" className="admin-gallery-carousel-button previous" onClick={() => showAdjacentPreview(-1)} aria-label="이전 이미지">‹</button>}<img key={previewing.id} src={previewing.image_url} alt={`${previewing.title} 미리보기`} />{rows.length > 1 && <button type="button" className="admin-gallery-carousel-button next" onClick={() => showAdjacentPreview(1)} aria-label="다음 이미지">›</button>}</div><footer><span>← → 방향키로 이동</span><a href={previewing.image_url} target="_blank" rel="noreferrer">원본 이미지 새 창에서 보기 ↗</a></footer></section></div>}
  </section>
}

export function ArtistDetailPage({ initial, onChanged }) {
  const [visibilitySaving, setVisibilitySaving] = useState(false)
  const [visibilityError, setVisibilityError] = useState('')
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileSaveError, setProfileSaveError] = useState('')
  const [artist, setArtist] = useState(initial)
  const [section, setSection] = useState(() => new URLSearchParams(window.location.search).get('section') === 'requests' ? 'requests' : 'artist')
  const [tab, setTab] = useState(() => {
    const requested = new URLSearchParams(window.location.search).get('tab')
    return ['profile', 'albums', 'fans', 'gallery'].includes(requested) ? requested : 'profile'
  })
  const selectTab = key => {
    const url = new URL(window.location.href)
    url.searchParams.set('tab', key)
    window.history.replaceState(window.history.state, '', url)
    setTab(key)
  }
  const selectSection = key => {
    const url = new URL(window.location.href)
    if (key === 'requests') url.searchParams.set('section', 'requests')
    else url.searchParams.delete('section')
    window.history.replaceState(window.history.state, '', url)
    setSection(key)
  }
  const [notice, setNotice] = useState('')
  const [profile, setProfile] = useState(() => ({ ...initial, name_ko: initial.name_ko || '', image_url: initial.image_url || '', profile_images: [...(initial.artist_profile_images || [])].sort((a, b) => a.display_order - b.display_order).map(item => item.image_url), description: initial.description || '', real_name: initial.real_name || '', role_description: initial.role_description || '', debut_text: initial.debut_text || '', agency: initial.agency || '', fandom_name: initial.fandom_name || '', hero_image_url: initial.hero_image_url || '', bio_text: (initial.bio_paragraphs || []).join('\n'), history_items: timelineDraft(initial.history_items), award_items: timelineDraft(initial.award_items), facebook_url: initial.facebook_url || '', x_url: initial.x_url || '', instagram_url: initial.instagram_url || '' }))
  const refresh = async message => { const next = await loadAdminArtistDetail(artist.id); setArtist(next); setNotice(message); onChanged() }
  const saveProfile = async event => {
    event.preventDefault()
    if (profileSaving) return
    setProfileSaving(true)
    setProfileSaveError('')
    try {
      await updateAdminArtist(artist.id, { ...profile, bio_paragraphs: parseLines(profile.bio_text), history_items: timelineValues(profile.history_items), award_items: timelineValues(profile.award_items) })
      setNotice('아티스트 전체 정보를 저장했습니다.')
      window.alert('저장 완료되었습니다.')
      try {
        await refresh('아티스트 전체 정보를 저장했습니다.')
      } catch {
        setProfileSaveError('저장은 완료됐지만 최신 정보를 다시 불러오지 못했습니다. 페이지를 새로고침해 주세요.')
      }
    } catch (error) {
      const message = error.message || '아티스트 정보를 저장하지 못했습니다. 다시 시도해 주세요.'
      setProfileSaveError(message)
      window.alert(`저장에 실패했습니다.\n${message}`)
    } finally {
      setProfileSaving(false)
    }
  }
  const update = (key, value) => setProfile(current => ({ ...current, [key]: value }))
  const toggleVisibility = async (nextStatus) => {
    if (visibilitySaving) return
    const active = nextStatus ? nextStatus === 'published' : !artist.active
    if (!window.confirm(active
      ? '이 아티스트를 사용자 페이지에 공개할까요? 저장된 정보만 공개되며, 비공개 앨범·갤러리는 그대로 유지됩니다.'
      : nextStatus === 'pending' ? '이 아티스트를 검토 대기로 변경할까요?' : '이 아티스트를 사용자 페이지에서 비공개로 변경할까요?')) return
    setVisibilitySaving(true)
    setVisibilityError('')
    try {
      const saved = await setAdminArtistVisibility(artist.id, active, nextStatus === 'pending')
      setArtist(current => ({ ...current, active: saved.active, review_pending: saved.review_pending }))
      setProfile(current => ({ ...current, active: saved.active, review_pending: saved.review_pending }))
      setNotice(saved.active ? '사용자 페이지에 공개했습니다. 비공개 앨범·갤러리는 별도로 공개해야 합니다.' : saved.review_pending ? '검토 대기로 변경했습니다.' : '비공개로 변경했습니다.')
      onChanged()
    } catch (error) {
      setVisibilityError(error.message || '공개 상태를 저장하지 못했습니다. 다시 시도해 주세요.')
    } finally {
      setVisibilitySaving(false)
    }
  }
  const requestCount = pendingCorrectionCount(artist)
  return <section className="admin-page-detail"><header className="admin-page-detail-head"><div><a href="/admin/artists">← 아티스트 목록</a><small>ARTIST DETAIL</small><h2>{artist.name_ko || artist.name}</h2></div><div className="admin-visibility-actions"><AdminDeleteArtist artist={artist} disabled={visibilitySaving} /><span role="status">{artistStatusLabels[artistStatus(artist)]}</span><button type="button" className="admin-primary" disabled={visibilitySaving} onClick={() => toggleVisibility()}>{visibilitySaving ? '변경 중…' : artist.active ? '비공개로 변경' : '공개로 변경'}</button></div></header>{!artist.active && <button type="button" disabled={visibilitySaving} onClick={() => toggleVisibility(artist.review_pending ? 'private' : 'pending')}>{artist.review_pending ? '비공개로 분류' : '검토 대기로 변경'}</button>}{visibilityError && <p className="admin-alert error" role="alert">{visibilityError}</p>}{notice && <p className="admin-alert" role="status">{notice}</p>}
    <nav className="admin-artist-section-tabs" aria-label="아티스트 상세 메뉴">
      <button type="button" className={section === 'artist' ? 'active' : ''} aria-current={section === 'artist' ? 'page' : undefined} onClick={() => selectSection('artist')}>아티스트 정보</button>
      <button type="button" className={section === 'requests' ? 'active' : ''} aria-current={section === 'requests' ? 'page' : undefined} onClick={() => selectSection('requests')}>수정 요청 <b>{requestCount}</b></button>
    </nav>
    {section === 'artist' ? <><nav className="admin-detail-tabs">{[['profile','소개'],['albums','앨범'],['fans','팬'],['gallery','갤러리']].map(([key,label]) => <button type="button" className={tab === key ? 'active' : ''} onClick={() => selectTab(key)} key={key}>{label}<b>{key === 'albums' ? artist.artist_albums?.length || 0 : key === 'fans' ? artist.artist_fans?.length || 0 : key === 'gallery' ? artist.artist_gallery_items?.length || 0 : ''}</b></button>)}</nav><div className="admin-page-detail-body">{tab === 'profile' ? <form className="admin-profile-editor" onSubmit={saveProfile}><AdminArtistImages profile={profile} gallery={artist.artist_gallery_items || []} onChange={update} /><div className="admin-form-columns"><label>URL Slug<input value={profile.slug} onChange={event => update('slug', event.target.value)} required /></label><label>영문 이름<input value={profile.name} onChange={event => update('name', event.target.value)} required /></label><label>한글 이름<input value={profile.name_ko} onChange={event => update('name_ko', event.target.value)} /></label><label>실명·공식명<input value={profile.real_name} onChange={event => update('real_name', event.target.value)} /></label><label>활동 분야<input value={profile.role_description} onChange={event => update('role_description', event.target.value)} /></label><label>데뷔<input value={profile.debut_text} onChange={event => update('debut_text', event.target.value)} /></label><label>소속사<input value={profile.agency} onChange={event => update('agency', event.target.value)} /></label><label>팬덤명<input value={profile.fandom_name} onChange={event => update('fandom_name', event.target.value)} /></label><label>팔로워<input type="number" min="0" value={profile.follower_count || 0} onChange={event => update('follower_count', event.target.value)} /></label><label>전체 방문자<input type="number" min="0" value={profile.visitor_total || 0} onChange={event => update('visitor_total', event.target.value)} /></label><label>오늘 방문자<input type="number" min="0" value={profile.visitor_today || 0} onChange={event => update('visitor_today', event.target.value)} /></label><label>Facebook URL<input value={profile.facebook_url} onChange={event => update('facebook_url', event.target.value)} /></label><label>X URL<input value={profile.x_url} onChange={event => update('x_url', event.target.value)} /></label><label>Instagram URL<input value={profile.instagram_url} onChange={event => update('instagram_url', event.target.value)} /></label></div><label>짧은 소개<textarea value={profile.description} onChange={event => update('description', event.target.value)} /></label><label>소개 본문 <small>문단마다 줄바꿈</small><textarea value={profile.bio_text} onChange={event => update('bio_text', event.target.value)} /></label><div className="admin-form-columns"><AdminTimelineEditor title="연혁" items={profile.history_items} onChange={items => update('history_items', items)} /><AdminTimelineEditor title="수상" items={profile.award_items} onChange={items => update('award_items', items)} /></div>{profileSaveError && <p className="admin-alert error admin-profile-save-message" role="alert">{profileSaveError}</p>}<button className="admin-primary" disabled={profileSaving}>{profileSaving ? '저장 중…' : '아티스트 전체 정보 저장'}</button></form> : <ArtistRelations artist={artist} type={tab} onRefresh={refresh} />}</div></> : <div className="admin-page-detail-body admin-correction-board-wrap"><AdminCorrectionRequests artistId={artist.id} /></div>}
  </section>
}

export function ArtistsPanel({ rows, onReload }) {
  const [requestsOnly, setRequestsOnly] = useState(false)
  const [status, setStatus] = useState('all')
  const [query, setQuery] = useState('')
  const totalRequests = rows.reduce((sum, artist) => sum + pendingCorrectionCount(artist), 0)
  const visible = filterAdminArtists(rows, { status, query, requestsOnly })
  return <>
    <div className="admin-correction-toolbar"><strong>미처리 수정 요청 {totalRequests}건</strong><label><input type="checkbox" checked={requestsOnly} onChange={e => setRequestsOnly(e.target.checked)} /> 요청 있는 아티스트만 보기</label></div>
    <div className="admin-artist-status-filters" role="group" aria-label="아티스트 상태 필터">{Object.entries(artistStatusLabels).map(([key, label]) => <button key={key} type="button" aria-pressed={status === key} onClick={() => setStatus(key)}>{label} <span>{key === 'all' ? rows.length : rows.filter(artist => artistStatus(artist) === key).length}</span></button>)}<span>최근 등록순</span></div>
    <div className="admin-search admin-section-search"><input value={query} onChange={event => setQuery(event.target.value)} placeholder="아티스트명, 소속사, 팬덤 검색" aria-label="아티스트 검색" />{query && <button type="button" onClick={() => setQuery('')}>지우기</button>}<span aria-live="polite">{visible.length}명</span></div>
    <section className="admin-card-grid">{visible.map(artist => <a href={`/admin/artists/${artist.id}`} key={artist.id}><img src={artist.image_url || '/images/icon_member.png'} alt="" /><span><small className={`admin-artist-status status-${artistStatus(artist)}`}>{artistStatusLabels[artistStatus(artist)]}</small><strong>{artist.name_ko || artist.name}</strong><small>등록 {artist.created_at ? new Date(artist.created_at).toLocaleDateString('ko-KR') : '일자 미상'}</small>{pendingCorrectionCount(artist) > 0 && <mark className="correction-count">수정 요청 {pendingCorrectionCount(artist)}건</mark>}<em>{artist.artist_albums?.length || 0}앨범 · {artist.artist_fans?.length || 0}팬 · {artist.artist_gallery_items?.length || 0}갤러리</em></span><b>상세 페이지</b></a>)}</section>
    {!visible.length && <p className="admin-empty">조건에 맞는 아티스트가 없습니다.</p>}
  </>
}

const emptyTrack = { track_number: 1, title: '', duration_text: '', lyrics_excerpt: '', youtube_url: '', active: true, display_order: 0 }

export function AlbumDetailPage({ initial, onChanged }) {
  const [album, setAlbum] = useState(initial)
  const [draft, setDraft] = useState(initial)
  const [editingTrack, setEditingTrack] = useState(null)
  const [notice, setNotice] = useState('')
  const refresh = async message => { const next = await loadAdminAlbumDetail(album.id); setAlbum(next); setDraft(next); setNotice(message); onChanged() }
  const update = (key, value) => setDraft(current => ({ ...current, [key]: value }))
  const saveAlbum = async event => { event.preventDefault(); await saveAdminArtistRelation('artist_albums', album.artist_id, draft); await refresh('앨범 상세 정보를 저장했습니다.') }
  const saveTrack = async event => { event.preventDefault(); await saveAdminAlbumTrack(album.id, editingTrack); setEditingTrack(null); await refresh('수록곡 정보를 저장했습니다.') }
  const removeTrack = async track => { if (!window.confirm(`${track.title} 수록곡을 삭제할까요?`)) return; await deleteAdminAlbumTrack(track.id); await refresh('수록곡을 삭제했습니다.') }
  const tracks = [...(album.artist_album_tracks || [])].sort((a, b) => Number(a.display_order || a.track_number) - Number(b.display_order || b.track_number))
  return <section className="admin-page-detail admin-album-page"><header className="admin-page-detail-head"><div><a href={`/admin/artists/${album.artist_id}?tab=albums`}>← {album.artists?.name_ko || album.artists?.name || '아티스트'} 상세</a><small>ALBUM DETAIL</small><h2>{album.title}</h2></div><span>{album.active ? '사용자 페이지 공개' : '비공개'}</span></header>{notice && <p className="admin-alert">{notice}</p>}<div className="admin-album-layout"><form className="admin-profile-editor admin-album-editor" onSubmit={saveAlbum}><header><div><small>ALBUM INFORMATION</small><h3>앨범 정보</h3></div>{draft.cover_url && <img src={draft.cover_url} alt={`${draft.title} 커버`} />}</header><RelationFields type="albums" value={draft} setValue={setDraft} /><label className="admin-check"><input type="checkbox" checked={draft.active} onChange={event => update('active', event.target.checked)} /> 사용자 페이지에 공개</label><button className="admin-primary">앨범 정보 저장</button></form><section className="admin-detail-section admin-track-manager"><header><div><small>TRACK LIST</small><h3>수록곡 관리</h3></div><button type="button" className="admin-add-button" onClick={() => setEditingTrack({ ...emptyTrack, track_number: tracks.length + 1, display_order: tracks.length + 1 })}>＋ 수록곡 추가</button></header><div className="admin-track-list">{tracks.map(track => <article key={track.id}><b>{String(track.track_number).padStart(2, '0')}</b><div><strong>{track.title}</strong><span>{track.duration_text || '재생 시간 미등록'}{track.youtube_url ? ' · YouTube 연결됨' : ''}</span><small>{track.active ? '공개' : '비공개'}</small></div><button type="button" onClick={() => setEditingTrack({ ...emptyTrack, ...track })}>수정</button><button type="button" className="danger" onClick={() => removeTrack(track)}>삭제</button></article>)}{!tracks.length && <p className="admin-empty">Supabase에 등록된 수록곡이 없습니다.</p>}</div>{editingTrack && <form className="admin-inline-editor" onSubmit={saveTrack}><header><strong>{editingTrack.id ? '수록곡 수정' : '수록곡 추가'}</strong><button type="button" onClick={() => setEditingTrack(null)}>×</button></header><div className="admin-form-columns"><label>트랙 번호<input type="number" min="1" value={editingTrack.track_number} onChange={event => setEditingTrack({ ...editingTrack, track_number: event.target.value })} required /></label><label>곡명<input value={editingTrack.title} onChange={event => setEditingTrack({ ...editingTrack, title: event.target.value })} required /></label><label>재생 시간<input value={editingTrack.duration_text || ''} onChange={event => setEditingTrack({ ...editingTrack, duration_text: event.target.value })} placeholder="03:42" /></label><label>표시 순서<input type="number" value={editingTrack.display_order} onChange={event => setEditingTrack({ ...editingTrack, display_order: event.target.value })} /></label><label>YouTube URL<input value={editingTrack.youtube_url || ''} onChange={event => setEditingTrack({ ...editingTrack, youtube_url: event.target.value })} /></label></div><label>가사·설명 미리보기<textarea value={editingTrack.lyrics_excerpt || ''} onChange={event => setEditingTrack({ ...editingTrack, lyrics_excerpt: event.target.value })} /></label><label className="admin-check"><input type="checkbox" checked={editingTrack.active} onChange={event => setEditingTrack({ ...editingTrack, active: event.target.checked })} /> 사용자 페이지에 공개</label><button className="admin-primary">수록곡 저장</button></form>}</section></div></section>
}

function CommentNode({ comment, rows, onChanged, depth = 0, visited = new Set() }) {
  const [draft, setDraft] = useState(comment.body)
  if (visited.has(comment.id)) return null
  const nextVisited = new Set(visited).add(comment.id)
  const children = rows.filter(row => row.parent_id === comment.id)
  const save = async () => { await updateAdminComment(comment.id, draft); await onChanged('댓글을 수정했습니다.') }
  const remove = async () => { if (!window.confirm('댓글을 삭제 처리할까요? 하위 댓글은 유지됩니다.')) return; await hideAdminComment(comment.id); await onChanged('댓글을 삭제 처리했습니다.') }
  return <article className={`admin-comment-node ${comment.deleted_at ? 'is-deleted' : ''}`} style={{ '--comment-depth': Math.min(depth, 6) }}><header><div><strong>{comment.deleted_at ? '삭제된 댓글' : comment.author_display_name}</strong><small>{formatDate(comment.created_at)}</small></div><span>👍 {comment.like_count}　👎 {comment.dislike_count}　↳ {children.length}</span></header>{comment.deleted_at ? <div className="admin-comment-tombstone">삭제된 댓글의 흔적입니다.</div> : <><textarea value={draft} onChange={event => setDraft(event.target.value)} /><footer><button type="button" onClick={save}>댓글 저장</button><button type="button" className="danger" onClick={remove}>삭제</button></footer></>}{children.length > 0 && <div className="admin-thread-children">{children.map(child => <CommentNode key={child.id} comment={child} rows={rows} onChanged={onChanged} depth={depth + 1} visited={nextVisited} />)}</div>}</article>
}

function PostDetail({ initial, artists, onClose, onChanged }) {
  const [post, setPost] = useState(initial)
  const [notice, setNotice] = useState('')
  const refresh = async message => { const next = await loadAdminPostDetail(post.id); setPost(next); setNotice(message); onChanged() }
  const update = (key, value) => setPost(current => ({ ...current, [key]: value }))
  const updateImageSource = (id, changes) => setPost(current => ({
    ...current,
    post_images: (current.post_images || []).map(image => image.id === id ? { ...image, ...changes } : image),
  }))
  const save = async event => { event.preventDefault(); await updateAdminPost(post.id, post); await refresh('포스트 전체 내용을 저장했습니다.') }
  const roots = post.comments.filter(comment => !comment.parent_id || !post.comments.some(parent => parent.id === comment.parent_id))
  const sortedImages = [...(post.post_images || [])].sort((a, b) => a.sort_order - b.sort_order)
  return <div className="admin-modal-backdrop admin-detail-backdrop"><section className="admin-modal admin-entity-detail post-admin-detail"><header><div><small>POST DETAIL</small><h2>{post.title}</h2></div><button type="button" onClick={onClose}>×</button></header>{notice && <p className="admin-alert">{notice}</p>}<form className="admin-profile-editor" onSubmit={save}><div className="admin-form-columns"><label>제목<input value={post.title} onChange={event => update('title', event.target.value)} required /></label><label>아티스트<select value={post.artist_id || ''} onChange={event => update('artist_id', event.target.value)}><option value="">연결 안 함</option>{artists.map(artist => <option value={artist.id} key={artist.id}>{artist.name_ko || artist.name}</option>)}</select></label></div><label>한 줄 내용<textarea className="short" value={post.summary || ''} onChange={event => update('summary', event.target.value)} /></label><label>본문 HTML<textarea className="post-body-editor" value={post.body_html || ''} onChange={event => update('body_html', event.target.value)} /></label><div className="admin-form-columns"><label>태그 <small>쉼표로 구분</small><input value={(post.tags || []).join(', ')} onChange={event => update('tags', event.target.value.split(',').map(value => value.trim()).filter(Boolean))} /></label><label>참조 URL<input value={post.reference_url || ''} onChange={event => update('reference_url', event.target.value)} /></label><label>출처명<input value={post.source_label || ''} onChange={event => update('source_label', event.target.value)} /></label><label>출처 원문 URL<input value={post.source_url || ''} onChange={event => update('source_url', event.target.value)} /></label><label>음원 제목<input value={post.audio_title || ''} onChange={event => update('audio_title', event.target.value)} /></label><label>음원 아티스트<input value={post.audio_artist || ''} onChange={event => update('audio_artist', event.target.value)} /></label><label>음원 URL<input value={post.audio_url || ''} onChange={event => update('audio_url', event.target.value)} /></label><label>상태<select value={post.status} onChange={event => update('status', event.target.value)}><option value="published">공개</option><option value="draft">임시저장</option><option value="archived">숨김</option></select></label></div><div className="admin-post-media"><header><div><strong>첨부 이미지 {sortedImages.length}개</strong><small>각 이미지의 원본 페이지를 선택적으로 등록할 수 있습니다.</small></div></header>{sortedImages.map((image, index) => { const sourceOpen = Boolean(image._sourceOpen || image.source_url || image.source_label); return <article key={image.id}><a className="admin-post-media-preview" href={image.image_url} target="_blank" rel="noreferrer"><img src={image.image_url} alt="" /><span>{index + 1}번 이미지 보기</span></a><div><strong>{index + 1}번 이미지</strong>{image.source_label && <small>{image.source_label}</small>}</div>{sourceOpen ? <><label><span>출처 URL <small>선택</small></span><input type="url" value={image.source_url || ''} onChange={event => updateImageSource(image.id, { source_url: event.target.value, _sourceOpen: true })} placeholder="https:// 원본 페이지 주소" /></label><button className="admin-image-source-remove" type="button" onClick={() => updateImageSource(image.id, { source_url: '', source_label: '', _sourceOpen: false })}>출처 제거</button></> : <button className="admin-image-source-add" type="button" onClick={() => updateImageSource(image.id, { _sourceOpen: true })}>+ 출처 등록</button>}</article>})}</div><button className="admin-primary">포스트 저장</button></form><section className="admin-post-comments"><header><div><small>COMMENTS</small><h3>포스트 댓글 관리</h3></div><span>{post.comments.filter(comment => !comment.deleted_at).length}개</span></header>{roots.map(comment => <CommentNode key={comment.id} comment={comment} rows={post.comments} onChanged={refresh} />)}{!roots.length && <p className="admin-empty">등록된 댓글이 없습니다.</p>}</section></section></div>
}

export function PostsPanel({ rows, artists, onReload }) {
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(null)
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [deleting, setDeleting] = useState(false)
  const keyword = safeLower(query.trim())
  const visible = rows.filter(post => !keyword || safeLower(`${post.title} ${post.summary} ${post.author_display_name} ${(post.tags || []).join(' ')}`).includes(keyword))
  const selectedCount = selectedIds.size
  const allVisibleSelected = visible.length > 0 && visible.every(post => selectedIds.has(post.id))
  useEffect(() => setSelectedIds(current => new Set([...current].filter(id => rows.some(post => post.id === id)))), [rows])
  const open = async post => setSelected(await loadAdminPostDetail(post.id))
  const toggle = id => setSelectedIds(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next })
  const toggleAllVisible = () => setSelectedIds(current => { const next = new Set(current); visible.forEach(post => allVisibleSelected ? next.delete(post.id) : next.add(post.id)); return next })
  const removeSelected = async () => {
    if (!selectedCount || !window.confirm(`선택한 포스트 ${selectedCount}개를 삭제할까요? 연결된 댓글과 반응도 함께 삭제되며 복구할 수 없습니다.`)) return
    setDeleting(true)
    try {
      const deleted = await deleteAdminPosts([...selectedIds])
      setSelectedIds(new Set())
      await onReload(`선택한 포스트 ${deleted.length}개를 삭제했습니다.`)
    } finally { setDeleting(false) }
  }
  return <><div className="admin-search admin-section-search"><input value={query} onChange={event => setQuery(event.target.value)} placeholder="제목, 본문 요약, 작성자, 태그 검색" aria-label="포스트 검색" />{query && <button type="button" onClick={() => setQuery('')}>지우기</button>}<span>{visible.length}건</span></div><div className="admin-member-selection admin-post-selection"><label><input type="checkbox" checked={allVisibleSelected} disabled={!visible.length || deleting} onChange={toggleAllVisible} /> 현재 목록 전체 선택</label><span>{selectedCount}개 선택</span><button type="button" disabled={!selectedCount || deleting} onClick={removeSelected}>{deleting ? '삭제 중…' : '선택 삭제'}</button></div><section className="admin-panel admin-table-wrap"><table><thead><tr><th className="admin-post-check-column"><span className="sr-only">선택</span></th><th>제목 / 작성자</th><th>등록일</th><th>조회</th><th>HEAT</th><th>댓글</th><th>상태</th><th></th></tr></thead><tbody>{visible.map(post => { const thumbnail = [...(post.post_images || [])].sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0))[0]?.image_url; return <tr className={selectedIds.has(post.id) ? 'selected' : ''} key={post.id}><td className="admin-post-check-column"><input type="checkbox" checked={selectedIds.has(post.id)} disabled={deleting} onChange={() => toggle(post.id)} aria-label={`${post.title} 선택`} /></td><td><div className="admin-post-list-title">{thumbnail ? <img src={thumbnail} alt="" loading="lazy" /> : <span className="admin-post-list-placeholder" aria-hidden="true">이미지 없음</span>}<span><strong>{post.title}</strong><small>@{post.author_display_name}</small></span></div></td><td>{formatDate(post.created_at)}</td><td>{Number(post.view_count).toLocaleString()}</td><td>{Number(post.vote_count).toLocaleString()}</td><td>{post.comments?.[0]?.count || 0}</td><td><span className={`admin-status ${post.status}`}>{post.status}</span></td><td><button type="button" className="admin-row-action" onClick={() => open(post)}>상세 관리</button></td></tr>})}</tbody></table></section>{selected && <PostDetail initial={selected} artists={artists} onClose={() => setSelected(null)} onChanged={() => onReload()} />}</>
}

export function CommentsPanel({ rows, onReload }) {
  const [query, setQuery] = useState('')
  const keyword = safeLower(query.trim())
  const matched = rows.filter(comment => !keyword || safeLower(`${comment.body} ${comment.author_display_name} ${comment.posts?.title}`).includes(keyword))
  const matchedIds = new Set(matched.map(comment => comment.id))
  const includeAncestors = comment => { let current = comment; const seen = new Set(); while (current?.parent_id && !seen.has(current.id)) { seen.add(current.id); matchedIds.add(current.parent_id); current = rows.find(row => row.id === current.parent_id) } }
  matched.forEach(includeAncestors)
  const visible = rows.filter(comment => matchedIds.has(comment.id))
  const roots = visible.filter(comment => !comment.parent_id || !visible.some(parent => parent.id === comment.parent_id))
  const posts = useMemo(() => [...new Set(visible.map(comment => comment.posts?.title).filter(Boolean))], [visible])
  return <><div className="admin-search admin-section-search"><input value={query} onChange={event => setQuery(event.target.value)} placeholder="댓글 내용, 작성자 또는 포스트 검색" aria-label="댓글 검색" />{query && <button type="button" onClick={() => setQuery('')}>지우기</button>}<span>{matched.length}개 · {posts.length}포스트</span></div><section className="admin-comment-management">{roots.map(comment => <section className="admin-comment-post" key={comment.id}><header><strong>{comment.posts?.title || '포스트 정보 없음'}</strong></header><CommentNode comment={comment} rows={visible.filter(row => row.post_id === comment.post_id)} onChanged={onReload} /></section>)}{!roots.length && <p className="admin-empty">검색 결과가 없습니다.</p>}</section></>
}
import AdminDeleteArtist from './AdminDeleteArtist'
