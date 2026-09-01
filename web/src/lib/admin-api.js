import { requireSupabase } from './supabase'

const throwIfError = result => {
  if (result.error) throw result.error
  return result.data
}

export const isAdminUser = user => user?.app_metadata?.role === 'admin'

export async function loadAdminDashboard() {
  const client = requireSupabase()
  const [members, artists, posts, comments, photos, votes, recentPosts, recentComments, auditLogs] = await Promise.all([
    client.from('profiles').select('*', { count: 'exact', head: true }),
    client.from('artists').select('*', { count: 'exact', head: true }),
    client.from('posts').select('*', { count: 'exact', head: true }),
    client.from('comments').select('*', { count: 'exact', head: true }).is('deleted_at', null),
    client.from('fan_photo_submissions').select('*', { count: 'exact', head: true }).eq('status', 'pending'),
    client.from('daily_artist_votes').select('*', { count: 'exact', head: true }).eq('vote_date', new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date())),
    client.from('posts').select('id,title,status,author_display_name,created_at,comments(count)').order('created_at', { ascending: false }).limit(6),
    client.from('comments').select('id,body,author_display_name,created_at,posts(title)').is('deleted_at', null).order('created_at', { ascending: false }).limit(6),
    client.from('admin_audit_logs').select('id,action,entity_type,entity_id,created_at').order('created_at', { ascending: false }).limit(8),
  ])
  const error = [members, artists, posts, comments, photos, votes, recentPosts, recentComments, auditLogs].find(result => result.error)?.error
  if (error) throw error
  return {
    summary: { members: members.count, artists: artists.count, posts: posts.count, comments: comments.count, photos: photos.count, votes: votes.count },
    recentPosts: recentPosts.data,
    recentComments: recentComments.data,
    auditLogs: auditLogs.data,
  }
}

export async function loadAdminMembers(query = '') {
  const client = requireSupabase()
  let request = client.from('profiles').select('id,display_name,avatar_url,bio,is_ai,created_at,updated_at').order('created_at', { ascending: false })
  if (query.trim()) {
    const value = query.trim()
    request = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
      ? request.or(`display_name.ilike.%${value}%,id.eq.${value}`)
      : request.ilike('display_name', `%${value}%`)
  }
  return throwIfError(await request)
}

export async function updateAdminMember(id, values) {
  return throwIfError(await requireSupabase().from('profiles').update({
    display_name: values.display_name.trim(),
    avatar_url: values.avatar_url.trim() || null,
    bio: values.bio.trim() || null,
    is_ai: Boolean(values.is_ai),
    updated_at: new Date().toISOString(),
  }).eq('id', id).select().single())
}

const albumTrackSelect = 'artist_album_tracks(id,album_id,track_number,title,duration_text,lyrics_excerpt,youtube_url,active,display_order,created_at,updated_at)'
const artistDetailSelect = `id,slug,name,name_ko,image_url,description,active,created_at,updated_at,real_name,role_description,debut_text,agency,fandom_name,hero_image_url,bio_paragraphs,history_items,award_items,follower_count,visitor_today,visitor_total,facebook_url,x_url,instagram_url,tracks(count),award_entries(count),posts(count),artist_albums(id,title,lead_track,release_date,album_type,track_count,cover_url,youtube_url,description,label,genre,external_url,active,display_order,created_at,updated_at,${albumTrackSelect}),artist_gallery_items(id,title,image_url,captured_on,active,display_order,created_at,updated_at),artist_fans(id,profile_id,display_name,handle,avatar_url,heat_percent,featured_rank,active,display_order,created_at,updated_at)`

export async function loadAdminArtists() {
  return throwIfError(await requireSupabase().from('artists').select(artistDetailSelect).order('active', { ascending: false }).order('name_ko'))
}

export async function loadAdminArtistDetail(id) {
  return throwIfError(await requireSupabase().from('artists').select(artistDetailSelect).eq('id', id).single())
}

export async function updateAdminArtist(id, values) {
  return throwIfError(await requireSupabase().from('artists').update({
    slug: values.slug.trim(),
    name: values.name.trim(),
    name_ko: values.name_ko.trim() || null,
    image_url: values.image_url.trim() || null,
    description: values.description.trim() || null,
    real_name: values.real_name?.trim() || null,
    role_description: values.role_description?.trim() || null,
    debut_text: values.debut_text?.trim() || null,
    agency: values.agency?.trim() || null,
    fandom_name: values.fandom_name?.trim() || null,
    hero_image_url: values.hero_image_url?.trim() || null,
    bio_paragraphs: Array.isArray(values.bio_paragraphs) ? values.bio_paragraphs.map(value => value.trim()).filter(Boolean) : [],
    history_items: Array.isArray(values.history_items) ? values.history_items : [],
    award_items: Array.isArray(values.award_items) ? values.award_items : [],
    follower_count: Math.max(0, Number(values.follower_count || 0)),
    visitor_today: Math.max(0, Number(values.visitor_today || 0)),
    visitor_total: Math.max(0, Number(values.visitor_total || 0)),
    facebook_url: values.facebook_url?.trim() || null,
    x_url: values.x_url?.trim() || null,
    instagram_url: values.instagram_url?.trim() || null,
    active: Boolean(values.active),
    updated_at: new Date().toISOString(),
  }).eq('id', id).select().single())
}

const relationPayloads = {
  artist_albums: values => ({ title: values.title?.trim(), lead_track: values.lead_track?.trim() || '', release_date: values.release_date || null, album_type: values.album_type?.trim() || '앨범', track_count: Math.max(0, Number(values.track_count || 0)), cover_url: values.cover_url?.trim() || null, youtube_url: values.youtube_url?.trim() || null, description: values.description?.trim() || null, label: values.label?.trim() || null, genre: values.genre?.trim() || null, external_url: values.external_url?.trim() || null, active: Boolean(values.active), display_order: Number(values.display_order || 0) }),
  artist_gallery_items: values => ({ title: values.title?.trim(), image_url: values.image_url?.trim(), captured_on: values.captured_on || null, active: Boolean(values.active), display_order: Number(values.display_order || 0) }),
  artist_fans: values => ({ profile_id: values.profile_id || null, display_name: values.display_name?.trim(), handle: values.handle?.trim(), avatar_url: values.avatar_url?.trim() || null, heat_percent: Math.max(0, Math.min(100, Number(values.heat_percent || 0))), featured_rank: values.featured_rank ? Number(values.featured_rank) : null, active: Boolean(values.active), display_order: Number(values.display_order || 0) }),
}

export async function saveAdminArtistRelation(table, artistId, values) {
  if (!relationPayloads[table]) throw new Error('지원하지 않는 아티스트 상세 유형입니다.')
  const payload = { ...relationPayloads[table](values), artist_id: artistId, updated_at: new Date().toISOString() }
  const request = values.id
    ? requireSupabase().from(table).update(payload).eq('id', values.id)
    : requireSupabase().from(table).insert(payload)
  return throwIfError(await request.select().single())
}

export async function deleteAdminArtistRelation(table, id) {
  if (!relationPayloads[table]) throw new Error('지원하지 않는 아티스트 상세 유형입니다.')
  return throwIfError(await requireSupabase().from(table).delete().eq('id', id).select().single())
}

export async function loadAdminAlbumDetail(id) {
  return throwIfError(await requireSupabase().from('artist_albums').select(`id,artist_id,title,lead_track,release_date,album_type,track_count,cover_url,youtube_url,description,label,genre,external_url,active,display_order,created_at,updated_at,artists(id,name,name_ko),${albumTrackSelect}`).eq('id', id).single())
}

const albumTrackPayload = values => ({
  track_number: Math.max(1, Number(values.track_number || 1)),
  title: values.title?.trim(),
  duration_text: values.duration_text?.trim() || null,
  lyrics_excerpt: values.lyrics_excerpt?.trim() || null,
  youtube_url: values.youtube_url?.trim() || null,
  active: Boolean(values.active),
  display_order: Number(values.display_order || 0),
  updated_at: new Date().toISOString(),
})

export async function saveAdminAlbumTrack(albumId, values) {
  const payload = { ...albumTrackPayload(values), album_id: albumId }
  const request = values.id
    ? requireSupabase().from('artist_album_tracks').update(payload).eq('id', values.id)
    : requireSupabase().from('artist_album_tracks').insert(payload)
  return throwIfError(await request.select().single())
}

export async function deleteAdminAlbumTrack(id) {
  return throwIfError(await requireSupabase().from('artist_album_tracks').delete().eq('id', id).select().single())
}

export async function loadAdminPosts() {
  return throwIfError(await requireSupabase().from('posts').select('id,title,summary,body_html,tags,reference_url,audio_url,audio_title,audio_artist,artist_id,author_display_name,status,view_count,vote_count,created_at,published_at,updated_at,post_images(id,image_url,sort_order),comments(count)').order('created_at', { ascending: false }))
}

export async function loadAdminPostDetail(id) {
  const client = requireSupabase()
  const [post, comments] = await Promise.all([
    client.from('posts').select('id,title,summary,body_html,tags,reference_url,audio_url,audio_title,audio_artist,artist_id,author_id,author_display_name,status,view_count,vote_count,created_at,published_at,updated_at,post_images(id,image_url,sort_order)').eq('id', id).single(),
    client.from('comments').select('id,post_id,parent_id,author_id,author_display_name,author_avatar_url,body,like_count,dislike_count,created_at,updated_at,deleted_at').eq('post_id', id).order('created_at'),
  ])
  if (post.error || comments.error) throw post.error || comments.error
  return { ...post.data, comments: comments.data }
}

export async function updateAdminPost(id, values) {
  return throwIfError(await requireSupabase().from('posts').update({
    title: values.title.trim(),
    summary: values.summary?.trim() || '',
    body_html: values.body_html || '',
    tags: Array.isArray(values.tags) ? values.tags : String(values.tags || '').split(',').map(value => value.trim()).filter(Boolean),
    reference_url: values.reference_url?.trim() || null,
    audio_url: values.audio_url?.trim() || null,
    audio_title: values.audio_title?.trim() || null,
    audio_artist: values.audio_artist?.trim() || null,
    artist_id: values.artist_id ? Number(values.artist_id) : null,
    status: values.status,
    published_at: values.published_at || null,
    updated_at: new Date().toISOString(),
  }).eq('id', id).select().single())
}

export async function updateAdminPostStatus(id, status) {
  if (!['draft', 'published', 'archived'].includes(status)) throw new Error('지원하지 않는 포스트 상태입니다.')
  return throwIfError(await requireSupabase().from('posts').update({ status, updated_at: new Date().toISOString() }).eq('id', id).select().single())
}

export async function loadAdminComments() {
  return throwIfError(await requireSupabase().from('comments').select('id,post_id,parent_id,body,author_display_name,author_avatar_url,like_count,dislike_count,created_at,updated_at,deleted_at,posts(id,title)').order('created_at', { ascending: false }))
}

export async function updateAdminComment(id, body) {
  const value = body.trim()
  if (!value) throw new Error('댓글 내용을 입력해 주세요.')
  return throwIfError(await requireSupabase().from('comments').update({ body: value, updated_at: new Date().toISOString() }).eq('id', id).select().single())
}

export async function hideAdminComment(id) {
  const now = new Date().toISOString()
  const client = requireSupabase()
  const comment = throwIfError(await client.from('comments').select('id,post_id,parent_id').eq('id', id).single())
  const tombstone = await client.from('comment_tombstones').upsert({ comment_id: id, post_id: comment.post_id, parent_id: comment.parent_id, deleted_at: now }, { onConflict: 'comment_id' })
  if (tombstone.error) throw tombstone.error
  return throwIfError(await client.from('comments').update({ deleted_at: now, updated_at: now }).eq('id', id).select().single())
}

export async function loadAdminFanPhotos() {
  const client = requireSupabase()
  const submissions = throwIfError(await client.from('fan_photo_submissions').select('id,submitter_id,submitter_name,note,status,admin_note,created_at,updated_at,fan_photo_submission_images(id,object_path,original_filename,width,height,sort_order)').order('created_at', { ascending: false }))
  return Promise.all(submissions.map(async submission => {
    const paths = submission.fan_photo_submission_images.map(image => image.object_path)
    if (!paths.length) return { ...submission, images: [] }
    const signed = throwIfError(await client.storage.from('fan-photo-submissions').createSignedUrls(paths, 900))
    return { ...submission, images: submission.fan_photo_submission_images.map((image, index) => ({ ...image, signed_url: signed[index]?.signedUrl || '' })) }
  }))
}

export async function reviewAdminFanPhoto(id, status, adminNote) {
  if (!['pending', 'approved', 'rejected'].includes(status)) throw new Error('지원하지 않는 검토 상태입니다.')
  return throwIfError(await requireSupabase().from('fan_photo_submissions').update({ status, admin_note: adminNote.trim() || null, updated_at: new Date().toISOString() }).eq('id', id).select().single())
}
