import { useEffect, useState } from 'react'

const imageFields = [['image_url', '대표 이미지'], ['hero_image_url', '배경 이미지']]

export default function AdminArtistImages({ profile, gallery = [], onChange }) {
  const inferMode = field => gallery.some(item => item.image_url === profile[field]) ? 'gallery' : 'url'
  const [modes, setModes] = useState(() => Object.fromEntries(imageFields.map(([field]) => [field, inferMode(field)])))

  useEffect(() => {
    setModes(Object.fromEntries(imageFields.map(([field]) => [field, inferMode(field)])))
  }, [profile.id])

  const chooseMode = (field, mode) => {
    if (modes[field] === mode) return
    setModes(current => ({ ...current, [field]: mode }))
    onChange(field, '')
  }

  return <section className="admin-artist-images">
    <h3>대표 이미지 설정</h3>
    <p>대표 이미지는 목록과 원형 프로필에, 배경 이미지는 큰 사진 영역에 사용됩니다. 각 이미지는 갤러리에서 선택하거나 URL을 직접 입력할 수 있습니다.</p>
    <div className="admin-image-previews">{imageFields.map(([field, label]) => <section className="admin-image-source-card" key={field}>
      <header><strong>{label}</strong><button type="button" className="admin-image-clear" disabled={!profile[field]} onClick={() => onChange(field, '')}>선택 해제</button></header>
      <div className="admin-image-preview">{profile[field] ? <img src={profile[field]} alt={`${label} 미리보기`} /> : <p>지정된 이미지 없음</p>}</div>
      <div className="admin-image-source-toggle" role="group" aria-label={`${label} 입력 방식`}>
        <button type="button" aria-pressed={modes[field] === 'gallery'} onClick={() => chooseMode(field, 'gallery')}>갤러리에서 선택</button>
        <button type="button" aria-pressed={modes[field] === 'url'} onClick={() => chooseMode(field, 'url')}>URL 직접 입력</button>
      </div>
      {modes[field] === 'url' ? <label className="admin-image-url-field">{label} URL<input type="url" value={profile[field] || ''} onChange={event => onChange(field, event.target.value)} placeholder="https://…" /></label> : <div className="admin-image-gallery-picker">
        <p>사용할 갤러리 이미지를 선택하세요.</p>
        <div>{gallery.map(item => <button type="button" key={item.id} aria-pressed={profile[field] === item.image_url} onClick={() => onChange(field, item.image_url)} title={item.title || '갤러리 이미지'}><img src={item.image_url} alt="" loading="lazy" /><span>{item.title || '이미지'}</span></button>)}</div>
        {!gallery.length && <p className="admin-image-empty">등록된 갤러리 이미지가 없습니다.</p>}
      </div>}
    </section>)}</div>
    <p className="admin-image-save-help">선택 후 아래의 ‘아티스트 전체 정보 저장’을 눌러야 반영됩니다. 비공개 갤러리 이미지를 선택하면 아티스트 공개 시 해당 이미지가 노출됩니다.</p>
  </section>
}
