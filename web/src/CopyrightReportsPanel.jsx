import { useState } from 'react'
import { reviewAdminCopyrightReport } from './lib/admin-api'

const typeLabels = { unauthorized_use: '저작물 무단 사용', ownership: '저작권 소유권 침해', license: '라이선스 조건 위반', impersonation: '권리자 사칭', other: '기타' }
const severityLabels = { low: '낮음', normal: '보통', high: '높음', urgent: '긴급' }
const statusLabels = { pending: '접수', reviewing: '검토 중', resolved: '처리 완료', rejected: '반려' }

export default function CopyrightReportsPanel({ rows, user, onReload }) {
  const [selected, setSelected] = useState(null)
  const [status, setStatus] = useState('pending')
  const [note, setNote] = useState('')
  const open = row => { setSelected(row); setStatus(row.status); setNote(row.admin_note || '') }
  const save = async event => { event.preventDefault(); await reviewAdminCopyrightReport(selected.id, status, note, user.id); setSelected(null); await onReload('저작권 신고 처리 상태를 저장했습니다.') }
  return <><section className="admin-panel admin-table-wrap copyright-admin-table"><table><thead><tr><th>접수일</th><th>신고 구분</th><th>신고자</th><th>침해 정도</th><th>상태</th><th></th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{new Date(row.created_at).toLocaleString('ko-KR')}</td><td>{typeLabels[row.report_type]}</td><td><strong>{row.reporter_email}</strong><small>{row.contact}</small></td><td><span className={`copyright-severity ${row.severity}`}>{severityLabels[row.severity]}</span></td><td><span className={`admin-status ${row.status}`}>{statusLabels[row.status]}</span></td><td><button className="admin-row-action" type="button" onClick={() => open(row)}>상세 관리</button></td></tr>)}</tbody></table>{!rows.length && <p className="admin-empty">접수된 저작권 신고가 없습니다.</p>}</section>{selected && <div className="admin-modal-backdrop" onMouseDown={event => event.target === event.currentTarget && setSelected(null)}><form className="admin-modal wide" onSubmit={save}><header><div><small>COPYRIGHT REPORT</small><h2>{typeLabels[selected.report_type]}</h2></div><button type="button" onClick={() => setSelected(null)}>×</button></header><div className="admin-copyright-meta"><span>신고자 <b>{selected.reporter_email}</b></span><span>연락처 <b>{selected.contact}</b></span><span>침해 정도 <b>{severityLabels[selected.severity]}</b></span></div><label>신고 내용<textarea value={selected.content} readOnly /></label><label>처리 상태<select value={status} onChange={event => setStatus(event.target.value)}><option value="pending">접수</option><option value="reviewing">검토 중</option><option value="resolved">처리 완료</option><option value="rejected">반려</option></select></label><label>관리자 처리 메모<textarea value={note} onChange={event => setNote(event.target.value)} maxLength="5000" /></label><button className="admin-primary">처리 내용 저장</button></form></div>}</>
}
