import { requireSupabase } from './supabase'

const imageName = value => /^https?:\/\//.test(value || '') ? value : value?.replace(/^\/images\//, '') ?? ''

export async function loadHomeData() {
  const client = requireSupabase()
  const [tracksResult, awardsResult, postsResult, artistsResult] = await Promise.all([
    client.from('tracks').select('id,artist_id,title,subtitle,cover_url,audio_url,display_order').eq('active', true).order('display_order'),
    client.from('award_entries').select('id,name,image_url,score,period,display_order').eq('active', true).order('display_order'),
    client.from('posts').select('id,author_id,title,summary,body_html,tags,reference_url,audio_url,audio_title,audio_artist,view_count,vote_count,author_display_name,published_at,created_at,post_images(image_url,sort_order),comments(count)').eq('status', 'published').order('published_at', { ascending: false }).order('created_at', { ascending: false }),
    client.from('artists').select('id,name,name_ko,image_url').eq('active', true).order('id'),
  ])
  const error = tracksResult.error || awardsResult.error || postsResult.error || artistsResult.error
  if (error) throw error
  return {
    tracks: tracksResult.data.map(row => [row.title, row.subtitle, imageName(row.cover_url), row]),
    awards: awardsResult.data.map(row => [row.name, Number(row.score).toLocaleString(), imageName(row.image_url), row]),
    artists: artistsResult.data,
    posts: postsResult.data.map(row => {
      const images = [...(row.post_images || [])].sort((a, b) => a.sort_order - b.sort_order).map(item => imageName(item.image_url))
      return [row.title, images[0] || 'post_list1.jpg', { ...row, images, comment_count: row.comments?.[0]?.count || 0 }]
    }),
  }
}

const seoulDate = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())

export async function loadDailyArtistVotes(userId) {
  const client = requireSupabase()
  const today = seoulDate()
  const [countsResult, ownResult] = await Promise.all([
    client.from('artist_daily_vote_counts').select('artist_id,vote_count').eq('vote_date', today),
    userId ? client.from('daily_artist_votes').select('artist_id,vote_date').eq('user_id', userId).eq('vote_date', today).maybeSingle() : Promise.resolve({ data: null, error: null }),
  ])
  if (countsResult.error || ownResult.error) throw countsResult.error || ownResult.error
  return { counts: Object.fromEntries(countsResult.data.map(row => [row.artist_id, Number(row.vote_count)])), ownVote: ownResult.data }
}

export async function castDailyArtistVote(userId, artistId) {
  const client = requireSupabase()
  const { error } = await client.from('daily_artist_votes').insert({ user_id: userId, artist_id: artistId })
  if (error) throw error
  return loadDailyArtistVotes(userId)
}

export async function loadComments(postId) {
  if (!postId) return []
  const { data, error } = await requireSupabase().from('comments').select('id,author_id,author_display_name,author_avatar_url,parent_id,body,like_count,dislike_count,created_at,updated_at').eq('post_id', postId).is('deleted_at', null).order('created_at', { ascending: true })
  if (error) throw error
  return data
}

export async function loadCommentReactions(userId, commentIds) {
  if (!userId || !commentIds.length) return []
  const { data, error } = await requireSupabase().from('comment_likes').select('comment_id,reaction').eq('user_id', userId).in('comment_id', commentIds)
  if (error) throw error
  return data
}

export async function setCommentReaction(commentId, userId, reaction) {
  const client = requireSupabase()
  const action = reaction
    ? client.from('comment_likes').upsert({ comment_id: commentId, user_id: userId, reaction }, { onConflict: 'comment_id,user_id' })
    : client.from('comment_likes').delete().eq('comment_id', commentId).eq('user_id', userId)
  const { error } = await action
  if (error) throw error
  const { data, error: countError } = await client.from('comments').select('like_count,dislike_count').eq('id', commentId).single()
  if (countError) throw countError
  return { likes: Number(data.like_count || 0), dislikes: Number(data.dislike_count || 0) }
}

export async function loadUserComments(userId) {
  if (!userId) return []
  const { data, error } = await requireSupabase().from('comments').select('id,post_id,author_id,author_display_name,author_avatar_url,body,created_at').eq('author_id', userId).is('deleted_at', null).order('created_at', { ascending: false })
  if (error) throw error
  return data
}

export async function updateComment(commentId, userId, body) {
  const { data, error } = await requireSupabase().from('comments').update({ body: body.trim(), updated_at: new Date().toISOString() }).eq('id', commentId).eq('author_id', userId).select('id,author_id,author_display_name,author_avatar_url,parent_id,body,like_count,dislike_count,created_at,updated_at').single()
  if (error) throw error
  return data
}

export async function deleteComment(commentId, userId) {
  const { error } = await requireSupabase().from('comments').update({ deleted_at: new Date().toISOString(), updated_at: new Date().toISOString() }).eq('id', commentId).eq('author_id', userId)
  if (error) throw error
}

export async function addComment(postId, user, body, parentId = null) {
  const client = requireSupabase()
  const { data: profile } = await client.from('profiles').select('display_name,avatar_url').eq('id', user.id).maybeSingle()
  const { data, error } = await client.from('comments').insert({
    post_id: postId,
    author_id: user.id,
    author_display_name: profile?.display_name || user.user_metadata?.display_name || user.email?.split('@')[0] || 'FAN',
    author_avatar_url: profile?.avatar_url || user.user_metadata?.avatar_url || null,
    parent_id: parentId,
    body,
  }).select('id,author_id,author_display_name,author_avatar_url,parent_id,body,like_count,dislike_count,created_at,updated_at').single()
  if (error) throw error
  return data
}

export async function publishPost(draft, user, imageFiles = [], imagePreviews = []) {
  const { data, error } = await requireSupabase().from('posts').insert({
    author_id: user.id,
    author_display_name: user.user_metadata?.display_name || user.email?.split('@')[0] || 'FAN',
    title: draft.title.trim(),
    summary: draft.summary.trim(),
    body_html: draft.content,
    tags: draft.tags.split(',').map(tag => tag.trim()).filter(Boolean),
    reference_url: draft.reference || null,
    audio_url: '/sample.mp3',
    audio_title: '비도 오고 그래서',
    audio_artist: '헤이즈 (Heize)',
    status: 'published',
    published_at: new Date().toISOString(),
  }).select().single()
  if (error) throw error
  if (imageFiles.length) {
    const uploaded = []
    const uploadedUrls = []
    for (const [index, file] of imageFiles.slice(0, 5).entries()) {
      const extension = file.name.split('.').pop()?.toLowerCase() || 'jpg'
      const objectPath = `${user.id}/posts/${data.id}/${crypto.randomUUID()}.${extension}`
      const upload = await requireSupabase().storage.from('fanheat-assets').upload(objectPath, file, { cacheControl: '3600', upsert: false, contentType: file.type })
      if (upload.error) throw upload.error
      const { data: publicAsset } = requireSupabase().storage.from('fanheat-assets').getPublicUrl(objectPath)
      uploaded.push({ post_id: data.id, image_url: publicAsset.publicUrl, sort_order: index })
      uploadedUrls.push(publicAsset.publicUrl)
    }
    const imagesResult = await requireSupabase().from('post_images').insert(uploaded)
    if (imagesResult.error) throw imagesResult.error
    const persistedHtml = imagePreviews.reduce((html, preview, index) => html.split(preview).join(uploadedUrls[index] || preview), draft.content)
    const updateResult = await requireSupabase().from('posts').update({ body_html: persistedHtml }).eq('id', data.id).eq('author_id', user.id)
    if (updateResult.error) throw updateResult.error
  }
  return data
}
