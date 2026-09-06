export default function AdminGallerySource({ item }) {
  const link = (value, label) => {
    try {
      const url = new URL(value)
      if (!['https:', 'http:'].includes(url.protocol)) return <span>{label}: 유효하지 않은 주소</span>
      return <a href={url.href} target="_blank" rel="noopener noreferrer">{label}: {url.hostname} · {url.href}</a>
    } catch { return <span>{label}: 미기록</span> }
  }
  return <div className="admin-gallery-source">
    <span>제공처: {item.source_provider || '미기록'}</span>
    <span>촬영자·저작자: {item.creator_name || '미기록'}</span>
    <span>라이선스: {item.license_name || '미기록'}</span>
    {link(item.license_url, '라이선스 조건')}
    <span>표기 문구: {item.attribution_text || '미기록'}</span>
    {link(item.source_page_url, '출처 페이지')}
    {link(item.original_image_url, '원본 이미지')}
    <span>출처 수집 시각: {item.source_collected_at ? new Date(item.source_collected_at).toLocaleString('ko-KR') : '미기록'}</span>
  </div>
}
