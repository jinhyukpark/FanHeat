import { useState } from 'react'

export default function AdminArtistThumbnail({ src, name }) {
  return <Thumbnail key={src || 'empty'} src={src} name={name} />
}

function Thumbnail({ src, name }) {
  const [attempt, setAttempt] = useState(0)
  const candidates = src ? [src] : []
  try {
    const url = new URL(src)
    if (url.protocol === 'https:' && url.hostname === 'yt3.ggpht.com') {
      url.hostname = 'yt3.googleusercontent.com'
      candidates.push(url.href)
    }
  } catch { /* Missing or relative image URL: retain the original candidate. */ }
  if (!candidates[attempt]) return <span className="admin-artist-image-error" role="img" aria-label={`${name} 이미지 로딩 실패`}>이미지 확인 필요</span>
  return <img src={candidates[attempt]} alt={`${name} 대표 이미지`} loading="lazy" referrerPolicy="no-referrer" onError={() => setAttempt(current => current + 1)} />
}
