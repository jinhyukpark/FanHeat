import { useEffect, useState } from 'react'
import { correctionCategories, correctionStates, correctionImageUrls, loadCorrectionRequests, reviewCorrection } from './lib/artist-corrections'
import './artist-corrections.css'

function RequestItem({ request, onSaved }) {
  const [urls, setUrls] = useState([])
  const [status, setStatus] = useState(request.status)
  const [note, setNote] = useState(request.admin_note)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const loadImages = async () => { try { setUrls(await correctionImageUrls(request.attachment_paths)); setError('') } catch (err) { setError(err.message) } }
  const save = async () => { setBusy(true); setError(''); try { await reviewCorrection(request.id, status, note); await onSaved() } catch (err) { setError(err.message) } finally { setBusy(false) } }
  const safeUrl = /^https?:\/\//i.test(request.evidence_url || '') ? request.evidence_url : null
  return <article className="admin-correction-item">
    <h4>{correctionCategories[request.category]} · {correctionStates[request.status]}</h4>
    <small>접수 {new Date(request.created_at).toLocaleString('ko-KR')} · 요청자 {request.requester_id}</small>
    <p className="correction-message">{request.message}</p>
    {safeUrl && <a href={safeUrl} target="_blank" rel="noopener noreferrer">근거: {safeUrl}</a>}
    {request.attachment_paths.length > 0 && <><button type="button" onClick={loadImages}>첨부 이미지 {request.attachment_paths.length}장 열기 / 링크 갱신</button><div className="correction-previews">{urls.map((item, i) => item.signedUrl ? <a href={item.signedUrl} key={item.path} target="_blank" rel="noopener noreferrer"><img src={item.signedUrl} alt={`수정 요청 첨부 ${i + 1}`} /></a> : <span key={i}>이미지를 불러오지 못했습니다.</span>)}</div></>}
    <div className="correction-review"><label>처리 상태<select value={status} onChange={e => setStatus(e.target.value)}>{Object.entries(correctionStates).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label><label>관리자 처리 메모<textarea maxLength={5000} value={note} onChange={e => setNote(e.target.value)} /></label><button type="button" disabled={busy} onClick={save}>{busy ? '저장 중…' : '처리 상태 저장'}</button></div>
    {request.reviewed_at && <small>최근 처리 {new Date(request.reviewed_at).toLocaleString('ko-KR')}</small>}
    {error && <p role="alert" className="correction-error">{error}</p>}
  </article>
}

export default function AdminCorrectionRequests({ artistId }) {
  const [requests, setRequests] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const load = async () => { try { setRequests(await loadCorrectionRequests(artistId)); setError('') } catch (err) { setError(err.message) } finally { setLoading(false) } }
  useEffect(() => { load() }, [artistId])
  return <section className="admin-correction-panel" id="correction-requests"><header><h3>정보 수정 요청 {requests.filter(r => ['pending', 'reviewing'].includes(r.status)).length}건 미처리</h3><button type="button" onClick={load}>새로고침</button></header><p>내용을 검토해 아티스트 정보를 별도로 수정한 뒤 처리 상태를 변경하세요.</p>{loading && <p>요청을 불러오는 중입니다.</p>}{error && <p role="alert">{error}</p>}{!loading && !error && !requests.length && <p>접수된 수정 요청이 없습니다.</p>}{requests.map(request => <RequestItem key={request.id} request={request} onSaved={load} />)}</section>
}
