export const artistStatusLabels = { all: '전체', published: '공개', pending: '대기 중', private: '비공개' }
export const artistStatus = artist => artist.active ? 'published' : artist.review_pending ? 'pending' : 'private'
export const pendingCorrectionCount = artist => (artist.artist_correction_requests || []).filter(r => ['pending', 'reviewing'].includes(r.status)).length
export function filterAdminArtists(rows, { status = 'all', query = '', requestsOnly = false } = {}) {
  const keyword = query.trim().toLocaleLowerCase()
  return rows.filter(artist => (status === 'all' || artistStatus(artist) === status)
    && (!requestsOnly || pendingCorrectionCount(artist) > 0)
    && (!keyword || [artist.name_ko, artist.name, artist.agency, artist.fandom_name].filter(Boolean).join(' ').toLocaleLowerCase().includes(keyword)))
    .sort((a, b) => (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0) || Number(b.id) - Number(a.id))
}
