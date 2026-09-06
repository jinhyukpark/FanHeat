import { requireSupabase } from './supabase'

export const correctionCategories = { profile: '기본 정보', biography: '소개', history: '연혁', awards: '수상', albums: '앨범·곡', gallery: '갤러리', other: '기타' }
export const correctionStates = { pending: '접수', reviewing: '검토 중', resolved: '처리 완료', rejected: '반려' }
const bucket = 'artist-corrections'
const unwrap = result => { if (result.error) throw result.error; return result.data }

export function validateCorrectionImages(files) {
  if (files.length > 5) throw new Error('이미지는 최대 5장까지 첨부할 수 있습니다.')
  for (const file of files) {
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) throw new Error('JPG, PNG, WebP 이미지만 첨부할 수 있습니다.')
    if (file.size > 5 * 1024 * 1024) throw new Error('이미지는 장당 5MB 이하로 첨부해 주세요.')
  }
}

export async function submitArtistCorrection(artistId, values, files, id) {
  validateCorrectionImages(files)
  const client = requireSupabase()
  const { user } = unwrap(await client.auth.getUser())
  if (!user) throw new Error('로그인 후 수정 요청을 보낼 수 있습니다.')
  const prior = unwrap(await client.from('artist_correction_requests').select('id').eq('id', id).maybeSingle())
  if (prior) return prior
  const uploaded = []
  try {
    for (let i = 0; i < files.length; i++) {
      const path = `${user.id}/${id}/${i + 1}`
      unwrap(await client.storage.from(bucket).upload(path, files[i], { upsert: false, contentType: files[i].type }))
      uploaded.push(path)
    }
    return unwrap(await client.from('artist_correction_requests').insert({
      id, artist_id: artistId, requester_id: user.id, category: values.category,
      message: values.message.trim(), evidence_url: values.evidence_url.trim() || null, attachment_paths: uploaded,
    }).select('id').single())
  } catch (error) {
    // A response can be lost after a successful insert. The policy preserves
    // attachments belonging to submitted requests during best-effort cleanup.
    if (uploaded.length) await client.storage.from(bucket).remove(uploaded).catch(() => {})
    throw error
  }
}

export async function loadCorrectionRequests(artistId) {
  let query = requireSupabase().from('artist_correction_requests').select('*').order('created_at', { ascending: false })
  if (artistId) query = query.eq('artist_id', artistId)
  return unwrap(await query)
}

export async function correctionImageUrls(paths) {
  if (!paths.length) return []
  return unwrap(await requireSupabase().storage.from(bucket).createSignedUrls(paths, 600))
}

export async function reviewCorrection(id, status, note) {
  const client = requireSupabase()
  const { user } = unwrap(await client.auth.getUser())
  return unwrap(await client.from('artist_correction_requests').update({ status, admin_note: note, reviewed_at: new Date().toISOString(), reviewed_by: user.id }).eq('id', id).select().single())
}
