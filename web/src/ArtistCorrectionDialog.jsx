import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { correctionCategories, submitArtistCorrection, validateCorrectionImages } from './lib/artist-corrections'
import './artist-corrections.css'

const acceptedImageTypes = 'image/jpeg,image/png,image/webp'

function UploadIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14.5v3A2.5 2.5 0 0 0 7.5 20h9a2.5 2.5 0 0 0 2.5-2.5v-3" />
  </svg>
}

function SuccessIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 12.5 3.2 3.2L17.5 8.5" /></svg>
}

export default function ArtistCorrectionDialog({ artist, onClose }) {
  const dialog = useRef(null)
  const fileInput = useRef(null)
  const requestId = useRef(crypto.randomUUID())
  const [values, setValues] = useState({ category: 'profile', message: '', evidence_url: '' })
  const [files, setFiles] = useState([])
  const [previews, setPreviews] = useState([])
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState(false)

  useEffect(() => { dialog.current.showModal() }, [])
  useEffect(() => {
    const urls = files.map(file => URL.createObjectURL(file))
    setPreviews(urls)
    return () => urls.forEach(URL.revokeObjectURL)
  }, [files])

  const addFiles = incomingFiles => {
    try {
      const next = [...files, ...Array.from(incomingFiles)]
      validateCorrectionImages(next)
      setFiles(next)
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }

  const submit = async event => {
    event.preventDefault()
    if (busy || sent) return
    setBusy(true)
    setError('')
    try {
      await submitArtistCorrection(artist.id, values, files, requestId.current)
      setSent(true)
    } catch (err) {
      setError(err.message || '요청을 보내지 못했습니다. 다시 시도해 주세요.')
    } finally {
      setBusy(false)
    }
  }

  return createPortal(<dialog
    ref={dialog}
    className="artist-correction-dialog"
    aria-labelledby="correction-title"
    onCancel={event => { event.preventDefault(); if (!busy) onClose() }}
  >
    <header className="correction-dialog-head">
      <div>
        <span className="correction-eyebrow">ARTIST CORRECTION</span>
        <h2 id="correction-title">{artist.name} 정보 수정 요청</h2>
        <p>정확한 아티스트 정보를 만드는 데 함께해 주세요.</p>
      </div>
      <button className="correction-close" type="button" disabled={busy} onClick={onClose} aria-label="수정 요청 닫기">×</button>
    </header>

    {sent ? <section className="correction-success" role="status">
      <span className="correction-success-icon"><SuccessIcon /></span>
      <h3>요청이 접수되었습니다</h3>
      <p>보내주신 내용과 자료는 관리자가 확인한 뒤 아티스트 정보에 반영합니다.</p>
      <button className="correction-primary" type="button" onClick={onClose}>확인</button>
    </section> : <form className="correction-form" onSubmit={submit}>
      <fieldset disabled={busy}>
        <section className="correction-section">
          <div className="correction-section-title">
            <span>01</span>
            <div><h3>어떤 정보를 수정할까요?</h3><p>현재 정보와 올바른 내용을 구체적으로 알려 주세요.</p></div>
          </div>

          <label className="correction-field">수정 항목
            <select value={values.category} onChange={event => setValues({ ...values, category: event.target.value })}>
              {Object.entries(correctionCategories).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>

          <label className="correction-field correction-message-field">
            <span className="correction-field-head"><span>요청 내용</span><small>{values.message.length.toLocaleString()} / 5,000자</small></span>
            <textarea
              required
              minLength={10}
              maxLength={5000}
              value={values.message}
              onChange={event => setValues({ ...values, message: event.target.value })}
              placeholder={'예) 현재 데뷔일이 2021년 10월 1일로 표시되어 있습니다.\n공식 홈페이지 기준 2021년 12월 1일로 수정해 주세요.'}
            />
          </label>

          <label className="correction-field">근거 URL <small>선택</small>
            <input
              type="url"
              pattern="https?://.*"
              value={values.evidence_url}
              onChange={event => setValues({ ...values, evidence_url: event.target.value })}
              placeholder="공식 홈페이지나 신뢰할 수 있는 출처의 URL"
            />
          </label>
        </section>

        <section className="correction-section">
          <div className="correction-section-title">
            <span>02</span>
            <div><h3>관련 이미지를 첨부해 주세요</h3><p>수정 내용을 확인할 수 있는 이미지가 있다면 함께 보내 주세요.</p></div>
          </div>

          <div
            className={`correction-dropzone${dragging ? ' is-dragging' : ''}`}
            onDragEnter={event => { event.preventDefault(); setDragging(true) }}
            onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy' }}
            onDragLeave={event => {
              if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false)
            }}
            onDrop={event => {
              event.preventDefault()
              setDragging(false)
              addFiles(event.dataTransfer.files)
            }}
          >
            <input
              ref={fileInput}
              className="correction-file-input"
              type="file"
              accept={acceptedImageTypes}
              multiple
              onChange={event => {
                addFiles(event.target.files)
                event.target.value = ''
              }}
            />
            <button type="button" onClick={() => fileInput.current?.click()}>
              <span className="correction-upload-icon"><UploadIcon /></span>
              <strong>{dragging ? '이미지를 여기에 놓아주세요' : '이미지를 끌어다 놓으세요'}</strong>
              <span>또는 클릭해서 파일 선택</span>
              <small>JPG, PNG, WebP · 장당 최대 5MB · 최대 5장</small>
            </button>
          </div>

          <div className="correction-privacy-note">
            <span aria-hidden="true">✓</span>
            첨부 이미지는 요청자와 관리자만 확인할 수 있습니다.
          </div>

          {previews.length > 0 && <div className="correction-previews" aria-label="선택한 이미지">
            {previews.map((url, index) => <div key={url}>
              <img src={url} alt={`첨부 이미지 ${index + 1}`} />
              <span>{index + 1}</span>
              <button type="button" onClick={() => setFiles(files.filter((_, fileIndex) => fileIndex !== index))} aria-label={`첨부 이미지 ${index + 1} 삭제`}>×</button>
            </div>)}
          </div>}
        </section>
      </fieldset>

      {error && <p className="correction-error" role="alert">{error}</p>}
      <footer className="correction-submit-bar">
        <button className="correction-secondary" type="button" disabled={busy} onClick={onClose}>취소</button>
        <button className="correction-primary" type="submit" disabled={busy}>{busy ? '전송 중…' : '수정 요청 보내기'}</button>
      </footer>
    </form>}
  </dialog>, document.body)
}
