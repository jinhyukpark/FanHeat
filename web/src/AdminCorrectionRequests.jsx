import { useEffect, useState } from 'react'
import { correctionCategories, correctionStates, correctionImageUrls, loadCorrectionRequests, reviewCorrection } from './lib/artist-corrections'
import './artist-corrections.css'

const pageSize = 20

function RequestItem({ request, number, onSaved }) {
  const [urls, setUrls] = useState([])
  const [imagesLoaded, setImagesLoaded] = useState(false)
  const [status, setStatus] = useState(request.status)
  const [note, setNote] = useState(request.admin_note || '')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const paths = request.attachment_paths || []
  const loadImages = async () => {
    if (imagesLoaded || !paths.length) return
    try {
      setUrls(await correctionImageUrls(paths))
      setImagesLoaded(true)
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }
  const save = async () => {
    setBusy(true)
    setError('')
    try {
      await reviewCorrection(request.id, status, note)
      await onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  const safeUrl = /^https?:\/\//i.test(request.evidence_url || '') ? request.evidence_url : null
  return <details className="admin-correction-row" onToggle={event => event.currentTarget.open && loadImages()}>
    <summary>
      <span className="correction-row-number">{number}</span>
      <strong>{correctionCategories[request.category] || '기타'}</strong>
      <span className="correction-row-subject">{request.message}</span>
      {paths.length > 0 ? <span className="correction-row-images" aria-label={`첨부 이미지 ${paths.length}장`}>이미지 {paths.length}</span> : <span>—</span>}
      <span className={`correction-row-state status-${request.status}`}>{correctionStates[request.status]}</span>
      <time dateTime={request.created_at}>{new Date(request.created_at).toLocaleDateString('ko-KR')}</time>
    </summary>
    <div className="admin-correction-row-detail">
      <small>접수 {new Date(request.created_at).toLocaleString('ko-KR')} · 요청자 {request.requester_id}</small>
      <p className="correction-message">{request.message}</p>
      {safeUrl && <a href={safeUrl} target="_blank" rel="noopener noreferrer">근거 URL 열기: {safeUrl}</a>}
      {paths.length > 0 && <section className="correction-attachment-section"><h4>첨부 이미지 {paths.length}장</h4>{!imagesLoaded && !error && <p>이미지를 불러오는 중입니다.</p>}<div className="correction-previews">{urls.map((item, i) => item.signedUrl ? <a href={item.signedUrl} key={item.path} target="_blank" rel="noopener noreferrer"><img src={item.signedUrl} alt={`수정 요청 첨부 ${i + 1}`} /></a> : <span key={item.path || i}>이미지를 불러오지 못했습니다.</span>)}</div></section>}
      <div className="correction-review"><label>처리 상태<select value={status} onChange={event => setStatus(event.target.value)}>{Object.entries(correctionStates).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label><label>관리자 처리 메모<textarea maxLength={5000} value={note} onChange={event => setNote(event.target.value)} /></label><button type="button" disabled={busy} onClick={save}>{busy ? '저장 중…' : '처리 상태 저장'}</button></div>
      {request.reviewed_at && <small>최근 처리 {new Date(request.reviewed_at).toLocaleString('ko-KR')}</small>}
      {error && <p role="alert" className="correction-error">{error}</p>}
    </div>
  </details>
}

export default function AdminCorrectionRequests({ artistId }) {
  const [requests, setRequests] = useState([])
  const [statusFilter, setStatusFilter] = useState('all')
  const [page, setPage] = useState(1)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const load = async () => {
    try {
      setRequests(await loadCorrectionRequests(artistId))
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [artistId])
  useEffect(() => { setPage(1) }, [statusFilter, artistId])
  const filtered = statusFilter === 'all' ? requests : requests.filter(request => request.status === statusFilter)
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize))
  const currentPage = Math.min(page, pageCount)
  const visible = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize)
  const pending = requests.filter(request => ['pending', 'reviewing'].includes(request.status)).length
  return <section className="admin-correction-panel" id="correction-requests">
    <header><div><small>CORRECTION REQUESTS</small><h3>정보 수정 요청</h3><p>총 {requests.length}건 · 미처리 {pending}건</p></div><button type="button" onClick={load}>새로고침</button></header>
    <div className="correction-board-toolbar"><label>처리 상태<select value={statusFilter} onChange={event => setStatusFilter(event.target.value)}><option value="all">전체 상태</option>{Object.entries(correctionStates).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label><span>{filtered.length}건</span></div>
    <div className="correction-board-head" aria-hidden="true"><span>번호</span><span>구분</span><span>요청 내용</span><span>첨부</span><span>상태</span><span>접수일</span></div>
    {loading && <p className="admin-empty">요청을 불러오는 중입니다.</p>}
    {error && <p role="alert" className="correction-error">{error}</p>}
    {!loading && !error && !visible.length && <p className="admin-empty">조건에 맞는 수정 요청이 없습니다.</p>}
    <div className="correction-board-list">{visible.map((request, index) => <RequestItem key={request.id} request={request} number={filtered.length - ((currentPage - 1) * pageSize + index)} onSaved={load} />)}</div>
    {pageCount > 1 && <nav className="correction-pagination" aria-label="수정 요청 페이지"><button type="button" disabled={currentPage === 1} onClick={() => setPage(value => Math.max(1, value - 1))}>이전</button><span>{currentPage} / {pageCount}</span><button type="button" disabled={currentPage === pageCount} onClick={() => setPage(value => Math.min(pageCount, value + 1))}>다음</button></nav>}
  </section>
}
