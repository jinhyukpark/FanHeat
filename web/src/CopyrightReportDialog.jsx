import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { submitCopyrightReport } from './lib/api'
import './copyright-report.css'

const initialValues = user => ({
  email: user?.email || '',
  contact: '',
  reportType: 'unauthorized_use',
  severity: 'normal',
  content: '',
})

export default function CopyrightReportDialog({ user }) {
  const [open, setOpen] = useState(false)
  const [values, setValues] = useState(() => initialValues(user))
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  useEffect(() => {
    const show = () => { setValues(initialValues(user)); setMessage(''); setOpen(true) }
    window.addEventListener('fanheat:open-copyright-report', show)
    return () => window.removeEventListener('fanheat:open-copyright-report', show)
  }, [user])
  useEffect(() => {
    if (!open) return undefined
    const close = event => event.key === 'Escape' && setOpen(false)
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', close)
    return () => { document.body.style.overflow = ''; window.removeEventListener('keydown', close) }
  }, [open])
  if (!open) return null
  const update = (key, value) => setValues(current => ({ ...current, [key]: value }))
  const submit = async event => {
    event.preventDefault(); setBusy(true); setMessage('')
    try {
      await submitCopyrightReport(user?.id, values)
      setMessage('저작권 신고가 접수되었습니다. 관리자가 확인 후 처리합니다.')
    } catch (error) { setMessage(error.message) }
    finally { setBusy(false) }
  }
  return createPortal(<div className="copyright-report-overlay" role="presentation" onMouseDown={event => event.target === event.currentTarget && setOpen(false)}>
    <form className="copyright-report-dialog" onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="copyright-report-title">
      <header><div><small>COPYRIGHT REPORT</small><h2 id="copyright-report-title">저작권 신고</h2><p>권리 침해 내용을 확인할 수 있도록 정확하게 작성해 주세요.</p></div><button type="button" onClick={() => setOpen(false)} aria-label="저작권 신고 닫기">×</button></header>
      <div className="copyright-report-grid"><label>신고자 이메일<input type="email" value={values.email} onChange={event => update('email', event.target.value)} maxLength="254" required /></label><label>연락처<input value={values.contact} onChange={event => update('contact', event.target.value)} maxLength="120" placeholder="전화번호 또는 연락 가능한 방법" required /></label><label>신고 구분<select value={values.reportType} onChange={event => update('reportType', event.target.value)}><option value="unauthorized_use">저작물 무단 사용</option><option value="ownership">저작권 소유권 침해</option><option value="license">라이선스 조건 위반</option><option value="impersonation">권리자 사칭</option><option value="other">기타</option></select></label><label>침해 정도<select value={values.severity} onChange={event => update('severity', event.target.value)}><option value="low">낮음</option><option value="normal">보통</option><option value="high">높음</option><option value="urgent">긴급</option></select></label></div>
      <label>신고 내용<textarea value={values.content} onChange={event => update('content', event.target.value)} minLength="20" maxLength="5000" placeholder="대상 포스트 URL, 권리 관계, 침해 내용을 20자 이상 입력해 주세요." required /><small>{values.content.length.toLocaleString()} / 5,000자</small></label>
      {message && <p className="copyright-report-message" role="status">{message}</p>}
      <footer><button type="button" onClick={() => setOpen(false)}>취소</button><button type="submit" disabled={busy || Boolean(message?.startsWith('저작권 신고가'))}>{busy ? '접수 중…' : '신고 접수'}</button></footer>
    </form>
  </div>, document.body)
}
