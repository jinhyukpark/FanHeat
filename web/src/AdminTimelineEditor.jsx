import { useId, useRef, useState } from 'react'

export function timelineDraft(items) {
  return (Array.isArray(items) ? items : []).map((item, index) => ({
    ...item, year: String(item.year ?? ''), text: String(item.text ?? ''), _editorKey: `saved-${index}`,
  }))
}

export function timelineValues(items) {
  return items.map(({ _editorKey, ...item }) => ({ ...item, year: item.year.trim(), text: item.text.trim() }))
}

export default function AdminTimelineEditor({ title, items, onChange }) {
  const id = useId()
  const sequence = useRef(0)
  const container = useRef(null)
  const drag = useRef(null)
  const [dragTarget, setDragTarget] = useState(null)
  const [announcement, setAnnouncement] = useState('')
  const update = (index, field, value) => onChange(items.map((item, i) => i === index ? { ...item, [field]: value } : item))
  const move = (index, destination) => {
    if (destination < 0 || destination >= items.length || destination === index) return
    const next = [...items]
    next.splice(destination, 0, next.splice(index, 1)[0])
    onChange(next)
    setAnnouncement(`${title} ${index + 1} 항목을 ${destination + 1}번째로 이동했습니다.`)
  }
  const endDrag = (event, commit) => {
    const current = drag.current
    drag.current = null
    setDragTarget(null)
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    if (commit && current) move(current.index, current.target)
  }
  return <section ref={container} className="admin-timeline-editor" aria-labelledby={`${id}-title`}>
    <header><h3 id={`${id}-title`}>{title} <span>{items.length}개</span></h3>
      <button type="button" className="admin-add-button" onClick={() => onChange([...items, { year: '', text: '', _editorKey: `${id}-${sequence.current++}` }])}>＋ {title} 추가</button>
    </header>
    <p id={`${id}-help`}>앞쪽 손잡이를 드래그해 순서를 바꾸세요. 키보드는 손잡이에서 ↑·↓ 키를 사용하세요. 수정 후 ‘아티스트 전체 정보 저장’을 눌러 주세요.</p>
    <span className="admin-timeline-announcement" role="status">{announcement}</span>
    {!items.length && <p className="admin-empty">등록된 {title}이 없습니다. 항목을 추가해 주세요.</p>}
    {items.map((item, index) => <fieldset key={item._editorKey} className={`admin-timeline-row${dragTarget === index ? ' drop-target' : ''}`}>
      <legend>{title} {index + 1}</legend>
      <button type="button" className="admin-timeline-handle" aria-label={`${title} ${index + 1} 순서 이동`} aria-describedby={`${id}-help`}
        onPointerDown={event => {
          if (event.button !== 0 || !event.isPrimary) return
          event.preventDefault()
          event.currentTarget.focus()
          event.currentTarget.setPointerCapture(event.pointerId)
          drag.current = { index, target: index }
          setDragTarget(index)
        }}
        onPointerMove={event => {
          if (!drag.current) return
          const rows = [...container.current.querySelectorAll('.admin-timeline-row')]
          const bounds = container.current.getBoundingClientRect()
          if (event.clientX < bounds.left || event.clientX > bounds.right) return
          let target = 0, distance = Infinity
          rows.forEach((row, i) => { const rect = row.getBoundingClientRect(); const delta = Math.abs(event.clientY - (rect.top + rect.height / 2)); if (delta < distance) { distance = delta; target = i } })
          drag.current.target = target
          setDragTarget(target)
        }}
        onPointerUp={event => endDrag(event, true)} onPointerCancel={event => endDrag(event, false)}
        onLostPointerCapture={() => { drag.current = null; setDragTarget(null) }}
        onKeyDown={event => {
          if (event.key === 'Escape') { drag.current = null; setDragTarget(null) }
          if (event.key === 'ArrowUp' || event.key === 'ArrowDown') { event.preventDefault(); move(index, index + (event.key === 'ArrowUp' ? -1 : 1)) }
        }}>⠿</button>
      <label>연도<input aria-label={`${title} ${index + 1} 연도`} value={item.year} onChange={event => update(index, 'year', event.target.value)} placeholder="예: 2026" required pattern=".*\S.*" /></label>
      <label>내용<input aria-label={`${title} ${index + 1} 내용`} value={item.text} onChange={event => update(index, 'text', event.target.value)} placeholder={`${title} 내용을 입력하세요`} required pattern=".*\S.*" /></label>
      <button type="button" className="admin-timeline-remove" onClick={() => onChange(items.filter((_, i) => i !== index))} aria-label={`${title} ${index + 1} 삭제`}>×</button>
    </fieldset>)}
  </section>
}
