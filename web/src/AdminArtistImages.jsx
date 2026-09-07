import { useEffect, useRef, useState } from 'react'
import { uploadAdminArtistProfileImage } from './lib/admin-api'

const imageFields = [['image_url', '프로필 이미지'], ['hero_image_url', '배경 이미지']]
const OUTPUT_SIZE = 800

function ProfileCropDialog({ artistId, source, onClose, onSaved }) {
  const canvasRef = useRef(null)
  const closeButtonRef = useRef(null)
  const imageRef = useRef(null)
  const dragRef = useRef(null)
  const [imageInfo, setImageInfo] = useState(null)
  const [crop, setCrop] = useState(null)
  const [status, setStatus] = useState('이미지를 불러오는 중입니다…')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const image = new Image()
    image.crossOrigin = 'anonymous'
    image.onload = () => {
      const scale = Math.min(720 / image.naturalWidth, 520 / image.naturalHeight, 1)
      const width = Math.max(1, Math.round(image.naturalWidth * scale))
      const height = Math.max(1, Math.round(image.naturalHeight * scale))
      const size = Math.round(Math.min(width, height) * .82)
      imageRef.current = image
      setImageInfo({ width, height, scale, naturalWidth: image.naturalWidth, naturalHeight: image.naturalHeight })
      setCrop({ x: Math.round((width - size) / 2), y: Math.round((height - size) / 2), size })
      const resolutionWarning = Math.min(image.naturalWidth, image.naturalHeight) < 400
        ? ' · 짧은 변이 400px 미만이라 확대하면 흐려질 수 있습니다.'
        : ''
      setStatus(`원본 ${image.naturalWidth}×${image.naturalHeight}px${resolutionWarning} 박스를 이동하거나 아래 조절 막대를 사용하세요.`)
    }
    image.onerror = () => setStatus('이 이미지는 원본 서버에서 편집을 허용하지 않습니다. 이미지 파일을 선택해 주세요.')
    image.src = source
    return () => { image.onload = null; image.onerror = null }
  }, [source])

  useEffect(() => {
    const canvas = canvasRef.current
    const image = imageRef.current
    if (!canvas || !imageInfo || !crop || !image) return
    canvas.width = imageInfo.width
    canvas.height = imageInfo.height
    const context = canvas.getContext('2d')
    context.drawImage(image, 0, 0, imageInfo.width, imageInfo.height)
    context.fillStyle = 'rgba(13, 10, 18, .58)'
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.save()
    context.beginPath()
    context.rect(crop.x, crop.y, crop.size, crop.size)
    context.clip()
    context.drawImage(image, 0, 0, imageInfo.width, imageInfo.height)
    context.restore()
    context.strokeStyle = '#ffffff'
    context.lineWidth = 3
    context.strokeRect(crop.x + 1.5, crop.y + 1.5, crop.size - 3, crop.size - 3)
    context.fillStyle = '#7656ef'
    context.fillRect(crop.x + crop.size - 18, crop.y + crop.size - 18, 18, 18)
  }, [crop, imageInfo])

  useEffect(() => {
    closeButtonRef.current?.focus()
    const close = event => { if (event.key === 'Escape' && !saving) onClose() }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [onClose, saving])

  const point = event => {
    const bounds = canvasRef.current.getBoundingClientRect()
    return {
      x: (event.clientX - bounds.left) * canvasRef.current.width / bounds.width,
      y: (event.clientY - bounds.top) * canvasRef.current.height / bounds.height,
    }
  }
  const pointerDown = event => {
    if (!crop) return
    const current = point(event)
    const resize = current.x >= crop.x + crop.size - 28 && current.y >= crop.y + crop.size - 28
    if (!resize && (current.x < crop.x || current.y < crop.y || current.x > crop.x + crop.size || current.y > crop.y + crop.size)) return
    event.currentTarget.setPointerCapture(event.pointerId)
    dragRef.current = { mode: resize ? 'resize' : 'move', start: current, crop }
  }
  const pointerMove = event => {
    const drag = dragRef.current
    if (!drag || !imageInfo) return
    const current = point(event)
    const dx = current.x - drag.start.x
    const dy = current.y - drag.start.y
    if (drag.mode === 'move') {
      setCrop({ ...drag.crop,
        x: Math.max(0, Math.min(imageInfo.width - drag.crop.size, drag.crop.x + dx)),
        y: Math.max(0, Math.min(imageInfo.height - drag.crop.size, drag.crop.y + dy)),
      })
      return
    }
    const maxSize = Math.min(imageInfo.width - drag.crop.x, imageInfo.height - drag.crop.y)
    const minSize = Math.min(80, maxSize)
    setCrop({ ...drag.crop, size: Math.max(minSize, Math.min(maxSize, drag.crop.size + Math.max(dx, dy))) })
  }
  const updateCrop = (field, value) => setCrop(current => {
    if (!current || !imageInfo) return current
    const number = Number(value)
    if (field === 'x') return { ...current, x: Math.max(0, Math.min(imageInfo.width - current.size, number)) }
    if (field === 'y') return { ...current, y: Math.max(0, Math.min(imageInfo.height - current.size, number)) }
    const maxSize = Math.min(imageInfo.width - current.x, imageInfo.height - current.y)
    return { ...current, size: Math.max(Math.min(80, maxSize), Math.min(maxSize, number)) }
  })
  const save = async () => {
    if (!imageInfo || !crop || !imageRef.current || saving) return
    setSaving(true)
    setStatus('800×800 이미지로 저장하는 중입니다…')
    try {
      const output = document.createElement('canvas')
      output.width = OUTPUT_SIZE
      output.height = OUTPUT_SIZE
      const ratio = 1 / imageInfo.scale
      output.getContext('2d').drawImage(imageRef.current, crop.x * ratio, crop.y * ratio, crop.size * ratio, crop.size * ratio, 0, 0, OUTPUT_SIZE, OUTPUT_SIZE)
      const blob = await new Promise(resolve => output.toBlob(resolve, 'image/webp', .9))
      if (!blob) throw new Error('이미지 파일을 만들 수 없습니다.')
      const saved = await uploadAdminArtistProfileImage(artistId, blob)
      onSaved(saved.image_url)
      onClose()
    } catch (error) {
      const cors = error?.name === 'SecurityError'
      setStatus(cors ? '원본 서버가 이미지 편집을 허용하지 않습니다. 이미지 파일을 선택해 주세요.' : error.message || '이미지를 저장하지 못했습니다.')
    } finally {
      setSaving(false)
    }
  }

  return <div className="admin-crop-backdrop" role="presentation" onMouseDown={event => event.target === event.currentTarget && !saving && onClose()}>
    <section className="admin-crop-dialog" role="dialog" aria-modal="true" aria-labelledby="admin-crop-title">
      <header><div><h3 id="admin-crop-title">프로필 이미지 자르기</h3><p>선택 영역을 800×800px WebP 이미지로 저장합니다.</p></div><button ref={closeButtonRef} type="button" onClick={onClose} disabled={saving} aria-label="이미지 자르기 닫기">×</button></header>
      <div className="admin-crop-stage"><canvas ref={canvasRef} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={() => { dragRef.current = null }} onPointerCancel={() => { dragRef.current = null }} role="img" aria-label="정사각형 자르기 미리보기. 드래그하여 위치와 크기를 조절할 수 있습니다." /></div>
      {crop && imageInfo && <div className="admin-crop-controls" aria-label="자르기 영역 정밀 조절">
        <label><span>가로 위치</span><input type="range" min="0" max={Math.max(0, Math.round(imageInfo.width - crop.size))} value={Math.round(crop.x)} onChange={event => updateCrop('x', event.target.value)} /></label>
        <label><span>세로 위치</span><input type="range" min="0" max={Math.max(0, Math.round(imageInfo.height - crop.size))} value={Math.round(crop.y)} onChange={event => updateCrop('y', event.target.value)} /></label>
        <label><span>선택 영역 크기</span><input type="range" min={Math.min(80, Math.round(Math.min(imageInfo.width - crop.x, imageInfo.height - crop.y)))} max={Math.round(Math.min(imageInfo.width - crop.x, imageInfo.height - crop.y))} value={Math.round(crop.size)} onChange={event => updateCrop('size', event.target.value)} /></label>
      </div>}
      <p className={status.includes('허용하지') || status.includes('못했습니다') ? 'error' : ''} role="status">{status}</p>
      <footer><button type="button" onClick={onClose} disabled={saving}>취소</button><button type="button" className="admin-primary" onClick={save} disabled={!crop || saving}>{saving ? '저장 중…' : '자른 이미지 적용 및 저장'}</button></footer>
    </section>
  </div>
}

export default function AdminArtistImages({ profile, gallery = [], onChange }) {
  const selectedProfileImages = profile.profile_images?.length ? profile.profile_images : (profile.image_url ? [profile.image_url] : [])
  const inferMode = field => gallery.some(item => item.image_url === profile[field]) ? 'gallery' : 'url'
  const [modes, setModes] = useState(() => Object.fromEntries(imageFields.map(([field]) => [field, inferMode(field)])))
  const [cropSource, setCropSource] = useState('')
  const localCropUrl = useRef('')

  useEffect(() => {
    setModes(Object.fromEntries(imageFields.map(([field]) => [field, inferMode(field)])))
  }, [profile.id])
  useEffect(() => () => { if (localCropUrl.current) URL.revokeObjectURL(localCropUrl.current) }, [])

  const chooseMode = (field, mode) => {
    if (modes[field] === mode) return
    setModes(current => ({ ...current, [field]: mode }))
    onChange(field, '')
  }
  const openFile = event => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 15 * 1024 * 1024) {
      window.alert('JPG, PNG, WebP 형식과 15MB 이하 이미지만 선택할 수 있습니다.')
      return
    }
    if (localCropUrl.current) URL.revokeObjectURL(localCropUrl.current)
    localCropUrl.current = URL.createObjectURL(file)
    setCropSource(localCropUrl.current)
  }
  const closeCrop = () => {
    setCropSource('')
    if (localCropUrl.current) {
      URL.revokeObjectURL(localCropUrl.current)
      localCropUrl.current = ''
    }
  }
  const setProfileImages = images => {
    const next = [...new Set(images.filter(Boolean))].slice(0, 10)
    onChange('profile_images', next)
    onChange('image_url', next[0] || '')
  }
  const toggleProfileImage = imageUrl => setProfileImages(selectedProfileImages.includes(imageUrl)
    ? selectedProfileImages.filter(value => value !== imageUrl)
    : [...selectedProfileImages, imageUrl])

  return <section className="admin-artist-images">
    <h3>프로필·배경 이미지 설정</h3>
    <p>프로필 이미지는 목록과 원형 프로필에, 배경 이미지는 아티스트 상세의 큰 사진 패널에 사용됩니다. 아래 미리보기는 원본 전체를 표시합니다.</p>
    <div className="admin-image-previews">{imageFields.map(([field, label]) => <section className={`admin-image-source-card ${field === 'image_url' ? 'profile-image' : 'background-image'}`} key={field}>
      <header><strong>{label}</strong><button type="button" className="admin-image-clear" disabled={!profile[field]} onClick={() => field === 'image_url' ? setProfileImages([]) : onChange(field, '')}>선택 해제</button></header>
      <div className="admin-image-preview">{profile[field] ? <img src={profile[field]} alt={`${label} 미리보기`} /> : <p>지정된 이미지 없음</p>}</div>
      <div className="admin-image-controls">
      <p>{field === 'image_url' ? '권장 800×800px · 최소 400×400px · 1:1 정사각형. 원형 표시를 위해 얼굴 주변에 여백을 남겨 주세요.' : '큰 사진 패널용 · 패널 비율에 따라 실제 화면에서는 일부가 잘릴 수 있습니다.'}</p>
      {field === 'image_url' && <div className="admin-profile-image-list"><header><strong>원형 프로필 슬라이드</strong><span>{selectedProfileImages.length} / 10</span></header><div>{selectedProfileImages.map((imageUrl, index) => <figure key={imageUrl}><img src={imageUrl} alt={`${index + 1}번째 프로필 이미지`} /><figcaption>{index + 1}</figcaption><button type="button" onClick={() => toggleProfileImage(imageUrl)} aria-label={`${index + 1}번째 프로필 이미지 삭제`}>×</button></figure>)}</div><small>선택한 순서대로 표시되며 첫 번째 이미지가 대표 이미지가 됩니다.</small></div>}
      {field === 'image_url' && <div className="admin-profile-crop-actions"><button type="button" disabled={!profile.image_url} onClick={() => setCropSource(profile.image_url)}>현재 이미지 자르기</button><label>이미지 파일 선택<input type="file" accept="image/jpeg,image/png,image/webp" onChange={openFile} /></label></div>}
      <div className="admin-image-source-toggle" role="group" aria-label={`${label} 입력 방식`}>
        <button type="button" aria-pressed={modes[field] === 'gallery'} onClick={() => chooseMode(field, 'gallery')}>갤러리에서 선택</button>
        <button type="button" aria-pressed={modes[field] === 'url'} onClick={() => chooseMode(field, 'url')}>URL 직접 입력</button>
      </div>
      {modes[field] === 'url' ? <label className="admin-image-url-field">{label} URL<input type="url" value={profile[field] || ''} onChange={event => onChange(field, event.target.value)} placeholder="https://…" /></label> : <div className="admin-image-gallery-picker">
        <p>사용할 갤러리 이미지를 선택하세요.</p>
        <div>{gallery.map(item => <button type="button" key={item.id} aria-pressed={field === 'image_url' ? selectedProfileImages.includes(item.image_url) : profile[field] === item.image_url} onClick={() => field === 'image_url' ? toggleProfileImage(item.image_url) : onChange(field, item.image_url)} title={field === 'image_url' ? `${item.title || '갤러리 이미지'} 프로필 선택` : item.title || '갤러리 이미지'}><img src={item.image_url} alt="" loading="lazy" /><span>{item.title || '이미지'}</span></button>)}</div>
        {!gallery.length && <p className="admin-image-empty">등록된 갤러리 이미지가 없습니다.</p>}
      </div>}
      </div>
    </section>)}</div>
    <p className="admin-image-save-help">일반 선택은 아래의 ‘아티스트 전체 정보 저장’을 눌러야 반영됩니다. 자르기 결과는 완료 버튼을 누르면 즉시 프로필에 저장됩니다.</p>
    {cropSource && <ProfileCropDialog artistId={profile.id} source={cropSource} onClose={closeCrop} onSaved={url => setProfileImages([...selectedProfileImages, url])} />}
  </section>
}
