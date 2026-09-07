import { requireSupabase } from './supabase'
import { PROFILE_DISPLAY_DEFAULTS, withProfileDisplayDefaults } from './profile-defaults'
import { MAX_FEATURED_MEDIA_COUNT, assertFeaturedMediaLimit } from './post-limits'

const imageName = value => /^https?:\/\//.test(value || '') ? value : value?.replace(/^\/images\//, '') ?? ''

const withApprovedGalleryItems = artist => artist ? {
  ...artist,
  artist_gallery_items: (artist.artist_gallery_items || []).filter(item => item.active === true && item.review_status === 'approved'),
} : artist

const optionalHttpUrl = (value, fieldLabel = '출처 URL') => {
  const raw = String(value || '').trim()
  if (!raw) return null
  try {
    const url = new URL(raw)
    if (!['http:', 'https:'].includes(url.protocol)) throw new Error()
    return url.href
  } catch {
    throw new Error(`${fieldLabel}은 http:// 또는 https:// 주소로 입력해 주세요.`)
  }
}

const sourceFields = source => ({
  source_label: String(source?.label || '').trim().slice(0, 120) || null,
  source_url: optionalHttpUrl(source?.url, '이미지 출처 URL'),
})

const postSourceRows = draft => {
  const rawSources = Array.isArray(draft.sourceLinks) && draft.sourceLinks.length
    ? draft.sourceLinks
    : draft.reference ? [{ label: draft.referenceLabel, url: draft.reference }] : []
  const seen = new Set()
  return rawSources.map(source => {
    const value = typeof source === 'string' ? { url: source } : source || {}
    const url = optionalHttpUrl(value.url || value.source_url, '글 출처 URL')
    if (!url || seen.has(url)) return null
    seen.add(url)
    return {
      label: String(value.label || value.source_label || '').trim().slice(0, 120) || null,
      url,
    }
  }).filter(Boolean).slice(0, 10)
}

const inlineSourceRows = (imageUrls, sources = []) => imageUrls.map((imageUrl, index) => ({
  image_url: imageUrl,
  ...sourceFields(sources[index]),
}))

export async function loadHomeData() {
  const client = requireSupabase()
  const [tracksResult, awardsResult, postsResult, artistsResult, heroResult] = await Promise.all([
    client.from('tracks').select('id,artist_id,title,subtitle,cover_url,audio_url,display_order').eq('active', true).order('display_order'),
    client.from('award_entries').select('id,name,image_url,score,period,display_order,artist:artists(id,slug,name,name_ko,image_url,description,real_name,role_description,debut_text,agency,fandom_name,hero_image_url,bio_paragraphs,history_items,award_items,follower_count,visitor_today,visitor_total,facebook_url,x_url,instagram_url,artist_albums(id,active,title,lead_track,release_date,album_type,track_count,cover_url,youtube_url,description,label,genre,external_url,display_order,artist_album_tracks(id,active,track_number,title,duration_text,lyrics_excerpt,youtube_url,display_order)),artist_gallery_items(id,active,review_status,title,image_url,original_image_url,captured_on,display_order,source_page_url,source_provider,creator_name,license_name,license_url,attribution_text),artist_fans(id,display_name,handle,avatar_url,heat_percent,featured_rank,display_order))').eq('active', true).order('display_order'),
    client.from('posts').select('id,author_id,title,summary,body_html,tags,reference_url,source_label,source_url,source_links,inline_image_sources,audio_url,audio_title,audio_artist,view_count,vote_count,author_display_name,published_at,created_at,post_images(image_url,sort_order,source_label,source_url),comments(count)').eq('status', 'published').order('published_at', { ascending: false }).order('created_at', { ascending: false }),
    client.from('artists').select('id,slug,name,name_ko,image_url,description,real_name,role_description,debut_text,agency,fandom_name,hero_image_url,bio_paragraphs,history_items,award_items,follower_count,visitor_today,visitor_total,facebook_url,x_url,instagram_url,artist_albums(id,active,title,lead_track,release_date,album_type,track_count,cover_url,youtube_url,description,label,genre,external_url,display_order,artist_album_tracks(id,active,track_number,title,duration_text,lyrics_excerpt,youtube_url,display_order)),artist_gallery_items(id,active,review_status,title,image_url,original_image_url,captured_on,display_order,source_page_url,source_provider,creator_name,license_name,license_url,attribution_text),artist_fans(id,display_name,handle,avatar_url,heat_percent,featured_rank,display_order)').eq('active', true).order('id'),
    client.from('home_hero_slides').select('id,layout_type,background_url,foreground_url,title,subtitle,display_order').eq('active', true).order('display_order').order('id'),
  ])
  const error = tracksResult.error || awardsResult.error || postsResult.error || artistsResult.error
  if (error) throw error
  const postAuthorIds = [...new Set(postsResult.data.map(row => row.author_id).filter(Boolean))]
  const postAuthorsResult = postAuthorIds.length
    ? await client.from('profiles').select('id,avatar_url').in('id', postAuthorIds)
    : { data: [], error: null }
  if (postAuthorsResult.error) throw postAuthorsResult.error
  const postAuthors = Object.fromEntries(postAuthorsResult.data.map(profile => [profile.id, profile]))
  const rankingPeriods = ['today', 'week', 'month']
  const rankingResults = await Promise.all(rankingPeriods.map(period => client.rpc('get_artist_activity_rankings', { p_period: period })))
  const artistRankings = Object.fromEntries(rankingPeriods.map((period, index) => [period, rankingResults[index].error ? [] : rankingResults[index].data]))
  return {
    tracks: tracksResult.data.map(row => [row.title, row.subtitle, imageName(row.cover_url), row]),
    awards: awardsResult.data.map(row => [row.name, Number(row.score).toLocaleString(), imageName(row.image_url), { ...row, ...(withApprovedGalleryItems(row.artist) || {}) }]),
    artists: artistsResult.data.map(withApprovedGalleryItems),
    artistRankings,
    heroSlides: heroResult.error ? [] : heroResult.data,
    posts: postsResult.data.map(row => {
      const postImages = [...(row.post_images || [])].sort((a, b) => a.sort_order - b.sort_order)
      const images = postImages.map(item => imageName(item.image_url))
      const imageSources = postImages.map(item => ({ label: item.source_label || '', url: item.source_url || '' }))
      return [row.title, images[0] || 'post_list1.jpg', { ...row, post_images: postImages, images, image_sources: imageSources, author_avatar_url: postAuthors[row.author_id]?.avatar_url || null, comment_count: row.comments?.[0]?.count || 0 }]
    }),
  }
}

const artistVisitorKey = () => {
  const storageKey = 'fanheat-artist-visitor-key'
  let value = window.localStorage.getItem(storageKey)
  if (!value) {
    value = crypto.randomUUID()
    window.localStorage.setItem(storageKey, value)
  }
  return value
}

export async function recordArtistClick(artistId) {
  if (!artistId) return
  const { error } = await requireSupabase().rpc('record_artist_click', { p_artist_id: artistId, p_visitor_key: artistVisitorKey() })
  if (error) throw error
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
  const today = seoulDate()
  const { data: updatedVote, error: updateError } = await client
    .from('daily_artist_votes')
    .update({ artist_id: artistId })
    .eq('user_id', userId)
    .eq('vote_date', today)
    .select('artist_id')
    .maybeSingle()
  if (updateError) throw updateError
  if (!updatedVote) {
    const { error: insertError } = await client.from('daily_artist_votes').insert({ user_id: userId, artist_id: artistId, vote_date: today })
    if (insertError) throw insertError
  }
  return loadDailyArtistVotes(userId)
}

export async function loadComments(postId) {
  if (!postId) return []
  const client = requireSupabase()
  const [comments, tombstones] = await Promise.all([
    client.from('comments').select('id,author_id,author_display_name,author_avatar_url,parent_id,body,like_count,dislike_count,created_at,updated_at,deleted_at').eq('post_id', postId).is('deleted_at', null).order('created_at', { ascending: true }),
    client.from('comment_tombstones').select('comment_id,parent_id,deleted_at').eq('post_id', postId).order('deleted_at', { ascending: true }),
  ])
  if (comments.error || tombstones.error) throw comments.error || tombstones.error
  return [...comments.data, ...tombstones.data.map(row => ({ id: row.comment_id, parent_id: row.parent_id, body: '', author_display_name: '삭제된 댓글', created_at: row.deleted_at, updated_at: row.deleted_at, deleted_at: row.deleted_at, like_count: 0, dislike_count: 0 }))]
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
  const { data, error } = await requireSupabase().from('comments').select('id,post_id,author_id,author_display_name,author_avatar_url,body,like_count,dislike_count,created_at').eq('author_id', userId).is('deleted_at', null).order('created_at', { ascending: false })
  if (error) throw error
  return data
}

export async function loadBestFriends(userId) {
  if (!userId) return []
  const { data, error } = await requireSupabase().rpc('get_my_best_friends')
  if (error) throw error
  return data || []
}

export async function loadPublicProfileFriends(userId) {
  if (!userId) return []
  const { data, error } = await requireSupabase().rpc('get_public_profile_friends', { target_user_id: userId })
  if (error) throw error
  return data || []
}

export async function loadFriendshipStatus(userId, friendId) {
  if (!userId || !friendId || userId === friendId) return 'none'
  const { data, error } = await requireSupabase().from('friendships').select('status').eq('owner_id', userId).eq('friend_id', friendId).maybeSingle()
  if (error) throw error
  return data?.status || 'none'
}

export async function sendFriendRequest(userId, friendId) {
  if (!userId || !friendId || userId === friendId) throw new Error('친구 요청 대상을 확인해 주세요.')
  const { data, error } = await requireSupabase().from('friendships').insert({ owner_id: userId, friend_id: friendId, status: 'pending', accepted_at: null }).select('status').single()
  if (error) throw error
  return data?.status || 'pending'
}

export async function cancelFriendRequest(userId, friendId) {
  if (!userId || !friendId) return
  const { error } = await requireSupabase().from('friendships').delete().eq('owner_id', userId).eq('friend_id', friendId).eq('status', 'pending')
  if (error) throw error
}

export async function updateComment(commentId, userId, body) {
  const { data, error } = await requireSupabase().from('comments').update({ body: body.trim(), updated_at: new Date().toISOString() }).eq('id', commentId).eq('author_id', userId).select('id,author_id,author_display_name,author_avatar_url,parent_id,body,like_count,dislike_count,created_at,updated_at').single()
  if (error) throw error
  return data
}

export async function deleteComment(commentId, userId) {
  const client = requireSupabase()
  const now = new Date().toISOString()
  const { data: comment, error: readError } = await client.from('comments').select('id,post_id,parent_id').eq('id', commentId).eq('author_id', userId).single()
  if (readError) throw readError
  const { error: tombstoneError } = await client.from('comment_tombstones').insert({ comment_id: commentId, post_id: comment.post_id, parent_id: comment.parent_id, deleted_at: now })
  if (tombstoneError) throw tombstoneError
  const { error } = await client.from('comments').update({ deleted_at: now, updated_at: now }).eq('id', commentId).eq('author_id', userId)
  if (error) throw error
}

export async function addComment(postId, user, body, parentId = null) {
  const client = requireSupabase()
  const { data: profile } = await client.from('profiles').select('display_name,avatar_url').eq('id', user.id).maybeSingle()
  const { data, error } = await client.from('comments').insert({
    post_id: postId,
    author_id: user.id,
    author_display_name: profile?.display_name || user.user_metadata?.display_name || user.email?.split('@')[0] || 'FAN',
    // Keep comment identity consistent with the avatar shown in the signed-in header.
    // The profile row can contain an older or no-longer-valid storage URL.
    author_avatar_url: user.user_metadata?.avatar_url || profile?.avatar_url || null,
    parent_id: parentId,
    body,
  }).select('id,author_id,author_display_name,author_avatar_url,parent_id,body,like_count,dislike_count,created_at,updated_at').single()
  if (error) throw error
  return data
}

const postImageTypes = new Map([
  ['image/jpeg', 'jpg'],
  ['image/png', 'png'],
  ['image/webp', 'webp'],
  ['image/gif', 'gif'],
])

async function uploadPostImage(client, file, userId, postId, kind = 'representative') {
  const extension = postImageTypes.get(file?.type)
  if (!extension || file.size > 10 * 1024 * 1024) throw new Error('게시글 이미지는 JPG, PNG, WebP, GIF 형식으로 10MB까지 등록할 수 있습니다.')
  const objectPath = `${userId}/posts/${postId}/${kind}-${crypto.randomUUID()}.${extension}`
  const upload = await client.storage.from('fanheat-assets').upload(objectPath, file, { cacheControl: '3600', upsert: false, contentType: file.type })
  if (upload.error) throw upload.error
  const { data: publicAsset } = client.storage.from('fanheat-assets').getPublicUrl(objectPath)
  return { objectPath, publicUrl: publicAsset.publicUrl }
}

export async function publishPost(draft, user, imageFiles = [], imagePreviews = [], inlineFiles = [], inlinePreviews = []) {
  assertFeaturedMediaLimit({ imageFiles, imagePreviews, mediaItems: draft.mediaItems || [] })
  const client = requireSupabase()
  const sources = postSourceRows(draft)
  const primarySource = sources[0] || {}
  const primaryMediaUrl = optionalHttpUrl(draft.mediaItems?.[0]?.url || draft.mediaUrl, '대표 미디어 URL')
  const { data, error } = await requireSupabase().from('posts').insert({
    author_id: user.id,
    author_display_name: user.user_metadata?.display_name || user.email?.split('@')[0] || 'FAN',
    title: draft.title.trim(),
    summary: draft.summary.trim(),
    body_html: draft.content,
    tags: draft.tags.split(',').map(tag => tag.trim()).filter(Boolean),
    reference_url: primaryMediaUrl || primarySource.url || null,
    source_label: primarySource.label || null,
    source_url: primarySource.url || null,
    source_links: sources,
    inline_image_sources: [],
    audio_url: '/sample.mp3',
    audio_title: '비도 오고 그래서',
    audio_artist: '헤이즈 (Heize)',
    status: 'published',
    published_at: new Date().toISOString(),
  }).select().single()
  if (error) throw error
  const uploadedPaths = []
  try {
    const representativeUrls = []
    for (const [index, file] of imageFiles.slice(0, MAX_FEATURED_MEDIA_COUNT).entries()) {
      const uploaded = await uploadPostImage(client, file, user.id, data.id)
      uploadedPaths.push(uploaded.objectPath)
      representativeUrls.push(uploaded.publicUrl)
    }
    if (representativeUrls.length) {
      const imagesResult = await client.from('post_images').insert(representativeUrls.map((imageUrl, index) => ({ post_id: data.id, image_url: imageUrl, sort_order: index, ...sourceFields(draft.imageSources?.[index]) })))
      if (imagesResult.error) throw imagesResult.error
    }
    const inlineUrls = []
    for (const file of inlineFiles.slice(0, 5)) {
      const uploaded = await uploadPostImage(client, file, user.id, data.id, 'inline')
      uploadedPaths.push(uploaded.objectPath)
      inlineUrls.push(uploaded.publicUrl)
    }
    const replacements = [...imagePreviews.map((preview, index) => [preview, representativeUrls[index]]), ...inlinePreviews.map((preview, index) => [preview, inlineUrls[index]])]
    const persistedHtml = replacements.reduce((html, [preview, url]) => url ? html.split(preview).join(url) : html, draft.content)
    const inlineImageSources = inlineSourceRows(inlineUrls, draft.inlineImageSources)
    if (persistedHtml !== draft.content || inlineImageSources.length) {
      const updateResult = await client.from('posts').update({ body_html: persistedHtml, inline_image_sources: inlineImageSources }).eq('id', data.id).eq('author_id', user.id)
      if (updateResult.error) throw updateResult.error
    }
    return { ...data, body_html: persistedHtml }
  } catch (uploadError) {
    if (uploadedPaths.length) await client.storage.from('fanheat-assets').remove(uploadedPaths)
    await client.from('posts').delete().eq('id', data.id).eq('author_id', user.id)
    throw uploadError
  }
}

export async function updatePost(postId, draft, user, imageFiles = [], imagePreviews = [], inlineFiles = [], inlinePreviews = []) {
  assertFeaturedMediaLimit({ imageFiles, imagePreviews, mediaItems: draft.mediaItems || [] })
  const client = requireSupabase()
  const sources = postSourceRows(draft)
  const primarySource = sources[0] || {}
  const primaryMediaUrl = optionalHttpUrl(draft.mediaItems?.[0]?.url || draft.mediaUrl, '대표 미디어 URL')
  const fields = {
    title: draft.title.trim(),
    summary: draft.summary.trim(),
    body_html: draft.content,
    tags: draft.tags.split(',').map(tag => tag.trim()).filter(Boolean),
    reference_url: primaryMediaUrl || primarySource.url || null,
    source_label: primarySource.label || null,
    source_url: primarySource.url || null,
    source_links: sources,
  }
  const { data, error } = await client.from('posts').update(fields).eq('id', postId).eq('author_id', user.id).select().single()
  if (error) throw error

  const uploadedByPreview = new Map()
  const uploadedPaths = []
  let fileIndex = 0
  for (const preview of imagePreviews) {
    if (!preview.startsWith('blob:')) continue
    const file = imageFiles[fileIndex++]
    if (!file) continue
    const uploaded = await uploadPostImage(client, file, user.id, postId)
    uploadedPaths.push(uploaded.objectPath)
    uploadedByPreview.set(preview, uploaded.publicUrl)
  }

  let inlineFileIndex = 0
  for (const preview of inlinePreviews.slice(0, 5)) {
    if (!preview.startsWith('blob:')) continue
    const file = inlineFiles[inlineFileIndex++]
    if (!file) continue
    const uploaded = await uploadPostImage(client, file, user.id, postId, 'inline')
    uploadedPaths.push(uploaded.objectPath)
    uploadedByPreview.set(preview, uploaded.publicUrl)
  }

  const finalImages = imagePreviews.slice(0, MAX_FEATURED_MEDIA_COUNT).map(preview => uploadedByPreview.get(preview) || preview)
  const deleteImages = await client.from('post_images').delete().eq('post_id', postId)
  if (deleteImages.error) throw deleteImages.error
  if (finalImages.length) {
    const insertImages = await client.from('post_images').insert(finalImages.map((imageUrl, index) => ({ post_id: postId, image_url: imageUrl, sort_order: index, ...sourceFields(draft.imageSources?.[index]) })))
    if (insertImages.error) throw insertImages.error
  }
  const persistedHtml = [...uploadedByPreview].reduce((html, [preview, url]) => html.split(preview).join(url), draft.content)
  const finalInlineImages = inlinePreviews.slice(0, 5).map(preview => uploadedByPreview.get(preview) || preview)
  const inlineImageSources = inlineSourceRows(finalInlineImages, draft.inlineImageSources)
  if (persistedHtml !== draft.content || inlineImageSources.length || Array.isArray(draft.inlineImageSources)) {
    const bodyResult = await client.from('posts').update({ body_html: persistedHtml, inline_image_sources: inlineImageSources }).eq('id', postId).eq('author_id', user.id)
    if (bodyResult.error) throw bodyResult.error
  }
  return { ...data, body_html: persistedHtml }
}

export async function submitFanPhotos(files, note, user) {
  const client = requireSupabase()
  const { data: submission, error: submissionError } = await client.from('fan_photo_submissions').insert({
    submitter_id: user.id,
    submitter_name: user.user_metadata?.display_name || user.email?.split('@')[0] || 'FAN',
    note: note.trim() || null,
  }).select('id,status,created_at').single()
  if (submissionError) throw submissionError

  const uploadedPaths = []
  try {
    const imageRows = []
    for (const [index, item] of files.entries()) {
      const extension = item.file.name.split('.').pop()?.toLowerCase() || 'jpg'
      const objectPath = `${user.id}/${submission.id}/${crypto.randomUUID()}.${extension}`
      const upload = await client.storage.from('fan-photo-submissions').upload(objectPath, item.file, {
        cacheControl: '3600',
        contentType: item.file.type,
        upsert: false,
      })
      if (upload.error) throw upload.error
      uploadedPaths.push(objectPath)
      imageRows.push({
        submission_id: submission.id,
        object_path: objectPath,
        original_filename: item.file.name,
        mime_type: item.file.type,
        size_bytes: item.file.size,
        width: item.width,
        height: item.height,
        sort_order: index,
      })
    }
    const imagesResult = await client.from('fan_photo_submission_images').insert(imageRows)
    if (imagesResult.error) throw imagesResult.error
    return submission
  } catch (error) {
    if (uploadedPaths.length) await client.storage.from('fan-photo-submissions').remove(uploadedPaths)
    await client.from('fan_photo_submissions').delete().eq('id', submission.id).eq('submitter_id', user.id)
    throw error
  }
}

export async function loadProfileGallery(userId) {
  if (!userId) return []
  const client = requireSupabase()
  const { data: rows, error } = await client.from('profile_gallery_images').select('id,user_id,object_path,original_filename,mime_type,size_bytes,width,height,sort_order,created_at').eq('user_id', userId).order('sort_order')
  if (error) throw error
  return Promise.all(rows.map(async row => {
    const { data, error: signedUrlError } = await client.storage.from('profile-gallery').createSignedUrl(row.object_path, 3600)
    if (signedUrlError) throw signedUrlError
    return { ...row, signedUrl: data.signedUrl }
  }))
}

export async function uploadProfileGalleryImages(items, userId, occupiedSlots = []) {
  const client = requireSupabase()
  const availableSlots = Array.from({ length: 10 }, (_, index) => index).filter(index => !occupiedSlots.includes(index))
  if (!userId || !items.length) return loadProfileGallery(userId)
  if (items.length > availableSlots.length) throw new Error('사진은 최대 10장까지 등록할 수 있습니다.')

  const uploadedPaths = []
  try {
    const rows = []
    for (const [index, item] of items.entries()) {
      const extension = item.file.name.split('.').pop()?.toLowerCase() || 'jpg'
      const objectPath = `${userId}/${crypto.randomUUID()}.${extension}`
      const upload = await client.storage.from('profile-gallery').upload(objectPath, item.file, {
        cacheControl: '3600',
        contentType: item.file.type,
        upsert: false,
      })
      if (upload.error) throw upload.error
      uploadedPaths.push(objectPath)
      rows.push({
        user_id: userId,
        object_path: objectPath,
        original_filename: item.file.name,
        mime_type: item.file.type,
        size_bytes: item.file.size,
        width: item.width,
        height: item.height,
        sort_order: availableSlots[index],
      })
    }
    const insert = await client.from('profile_gallery_images').insert(rows)
    if (insert.error) throw insert.error
    return loadProfileGallery(userId)
  } catch (error) {
    if (uploadedPaths.length) await client.storage.from('profile-gallery').remove(uploadedPaths)
    throw error
  }
}

export async function deleteProfileGalleryImage(image, userId) {
  const client = requireSupabase()
  const remove = await client.storage.from('profile-gallery').remove([image.object_path])
  if (remove.error) throw remove.error
  const deleted = await client.from('profile_gallery_images').delete().eq('id', image.id).eq('user_id', userId)
  if (deleted.error) throw deleted.error
}

const profileFields = 'id,display_name,avatar_url,bio,cover_url,avatar_object_path,cover_object_path,avatar_urls,avatar_object_paths,cover_urls,cover_object_paths,profile_headline,facebook_url,x_url,instagram_url,tiktok_url,youtube_url,favorite_track_id,is_ai,updated_at'

export async function loadProfileCustomization(userId) {
  if (!userId) return null
  const { data, error } = await requireSupabase().from('profiles').select(profileFields).eq('id', userId).single()
  if (error) throw error
  return withProfileDisplayDefaults(data)
}

export async function saveProfileCustomization({ userId, values, avatarItems = [], coverItems = [] }) {
  if (!userId) throw new Error('로그인이 필요합니다.')
  const client = requireSupabase()
  if (avatarItems.length > 5 || coverItems.length > 5) throw new Error('프로필 사진과 배경 이미지는 각각 최대 5장까지 등록할 수 있습니다.')
  const { data: current, error: currentError } = await client.from('profiles').select('avatar_object_path,cover_object_path,avatar_object_paths,cover_object_paths').eq('id', userId).single()
  if (currentError) throw currentError
  const uploaded = []
  const upload = async (file, kind) => {
    if (!file) return null
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) throw new Error('프로필과 배경 이미지는 JPG, PNG, WebP 형식으로 5MB까지 등록할 수 있습니다.')
    const extension = file.name.split('.').pop()?.toLowerCase() || 'jpg'
    const path = `${userId}/profile/${kind}-${crypto.randomUUID()}.${extension}`
    const result = await client.storage.from('fanheat-assets').upload(path, file, { cacheControl: '3600', contentType: file.type, upsert: false })
    if (result.error) throw result.error
    uploaded.push(path)
    return { path, url: client.storage.from('fanheat-assets').getPublicUrl(path).data.publicUrl }
  }
  try {
    const saveItems = async (items, kind) => {
      const saved = []
      for (const item of items) {
        if (item.file) saved.push(await upload(item.file, kind))
        else if (item.url) saved.push({ url: item.url, path: item.path || null })
      }
      return saved
    }
    const avatars = await saveItems(avatarItems, 'avatar')
    const covers = await saveItems(coverItems, 'cover')
    const payload = {
      display_name: values.displayName.trim(),
      profile_headline: values.headline.trim().slice(0, 40) || PROFILE_DISPLAY_DEFAULTS.profile_headline,
      bio: values.bio.trim() || PROFILE_DISPLAY_DEFAULTS.bio,
      facebook_url: values.facebookUrl.trim() || PROFILE_DISPLAY_DEFAULTS.facebook_url,
      x_url: values.xUrl.trim() || PROFILE_DISPLAY_DEFAULTS.x_url,
      instagram_url: values.instagramUrl.trim() || PROFILE_DISPLAY_DEFAULTS.instagram_url,
      tiktok_url: values.tiktokUrl.trim() || null,
      youtube_url: values.youtubeUrl.trim() || null,
      favorite_track_id: values.favoriteTrackId ? Number(values.favoriteTrackId) : null,
      updated_at: new Date().toISOString(),
      avatar_urls: avatars.map(item => item.url),
      avatar_object_paths: avatars.map(item => item.path || ''),
      cover_urls: covers.map(item => item.url),
      cover_object_paths: covers.map(item => item.path || ''),
      avatar_url: avatars[0]?.url || null,
      avatar_object_path: avatars[0]?.path || null,
      cover_url: covers[0]?.url || null,
      cover_object_path: covers[0]?.path || null,
    }
    const { data, error } = await client.from('profiles').update(payload).eq('id', userId).select(profileFields).single()
    if (error) throw error
    await client.auth.updateUser({ data: { display_name: data.display_name, avatar_url: data.avatar_url } })
    const retainedPaths = new Set([...avatars, ...covers].map(item => item.path).filter(Boolean))
    const obsolete = [...new Set([
      ...(current.avatar_object_paths || []),
      ...(current.cover_object_paths || []),
      current.avatar_object_path,
      current.cover_object_path,
    ].filter(path => path && !retainedPaths.has(path)))]
    if (obsolete.length) await client.storage.from('fanheat-assets').remove(obsolete)
    return data
  } catch (error) {
    if (uploaded.length) await client.storage.from('fanheat-assets').remove(uploaded)
    throw error
  }
}

export async function loadFanStats(userId) {
  if (!userId) throw new Error('사용자를 확인할 수 없습니다.')
  const { data, error } = await requireSupabase().rpc('get_fan_stats', { target: userId })
  if (error || !data) throw new Error('활동 통계를 불러오지 못했습니다.')
  return data
}

export async function loadFanCred(userId) {
  if (!userId) return 0
  const { data, error } = await requireSupabase().from('fan_cred_events').select('points').eq('recipient_id', userId)
  if (error) throw error
  return data.reduce((total, event) => total + Number(event.points || 0), 0)
}

export async function setPostVote(postId, userId, voted) {
  const client = requireSupabase()
  const result = voted
    ? await client.from('post_votes').insert({ post_id: postId, user_id: userId })
    : await client.from('post_votes').delete().eq('post_id', postId).eq('user_id', userId)
  if (result.error && result.error.code !== '23505') throw result.error
}

export async function loadPostVote(postId, userId) {
  if (!postId || !userId) return false
  const { data, error } = await requireSupabase().from('post_votes').select('post_id').eq('post_id', postId).eq('user_id', userId).maybeSingle()
  if (error) throw error
  return Boolean(data)
}

export async function loadPostBookmark(postId, userId) {
  if (!postId || !userId) return false
  const { data, error } = await requireSupabase().from('post_bookmarks').select('post_id').eq('post_id', postId).eq('user_id', userId).maybeSingle()
  if (error) throw error
  return Boolean(data)
}

export async function setPostBookmark(postId, userId, bookmarked) {
  const client = requireSupabase()
  const result = bookmarked
    ? await client.from('post_bookmarks').insert({ post_id: postId, user_id: userId })
    : await client.from('post_bookmarks').delete().eq('post_id', postId).eq('user_id', userId)
  if (result.error && result.error.code !== '23505') throw result.error
}

export async function loadUserBookmarks(userId) {
  if (!userId) return []
  const { data, error } = await requireSupabase().from('post_bookmarks').select('post_id,created_at').eq('user_id', userId).order('created_at', { ascending: false })
  if (error) throw error
  return data
}

const messageProfileFields = 'id,display_name,avatar_url'
const messageFields = `id,sender_id,recipient_id,reply_to_id,body,read_at,created_at,sender:profiles!private_messages_sender_id_fkey(${messageProfileFields}),recipient:profiles!private_messages_recipient_id_fkey(${messageProfileFields})`

export async function loadPrivateMessages(userId) {
  if (!userId) return []
  const { data, error } = await requireSupabase()
    .from('private_messages')
    .select(messageFields)
    .or(`sender_id.eq.${userId},recipient_id.eq.${userId}`)
    .order('created_at', { ascending: false })
    .limit(100)
  if (error) throw error
  return data
}

export async function loadUnreadMessageCount(userId) {
  if (!userId) return 0
  const { count, error } = await requireSupabase()
    .from('private_messages')
    .select('id', { count: 'exact', head: true })
    .eq('recipient_id', userId)
    .is('read_at', null)
  if (error) throw error
  return count || 0
}

export async function loadMessageContacts(userId) {
  if (!userId) return []
  const { data, error } = await requireSupabase()
    .from('profiles')
    .select(messageProfileFields)
    .neq('id', userId)
    .order('display_name')
    .limit(100)
  if (error) throw error
  return data
}

export async function sendPrivateMessage({ senderId, recipientId, body, replyToId = null }) {
  const message = body.trim()
  if (!senderId || !recipientId) throw new Error('받는 사람을 선택해 주세요.')
  if (!message) throw new Error('쪽지 내용을 입력해 주세요.')
  const { data, error } = await requireSupabase()
    .from('private_messages')
    .insert({ sender_id: senderId, recipient_id: recipientId, body: message, reply_to_id: replyToId })
    .select(messageFields)
    .single()
  if (error) throw error
  return data
}

export async function markPrivateMessageRead(messageId, userId) {
  if (!messageId || !userId) return
  const { error } = await requireSupabase()
    .from('private_messages')
    .update({ read_at: new Date().toISOString() })
    .eq('id', messageId)
    .eq('recipient_id', userId)
    .is('read_at', null)
  if (error) throw error
}

export async function loadMessageBlocks(userId) {
  if (!userId) return []
  const { data, error } = await requireSupabase()
    .from('message_blocks')
    .select(`blocker_id,blocked_user_id,created_at,blocked:profiles!message_blocks_blocked_user_id_fkey(${messageProfileFields})`)
    .eq('blocker_id', userId)
    .order('created_at', { ascending: false })
  if (error) throw error
  return data
}

export async function setMessageBlock(blockerId, blockedUserId, blocked) {
  if (!blockerId || !blockedUserId) throw new Error('차단할 사용자를 확인할 수 없습니다.')
  const client = requireSupabase()
  const result = blocked
    ? await client.from('message_blocks').upsert({ blocker_id: blockerId, blocked_user_id: blockedUserId }, { onConflict: 'blocker_id,blocked_user_id' })
    : await client.from('message_blocks').delete().eq('blocker_id', blockerId).eq('blocked_user_id', blockedUserId)
  if (result.error) throw result.error
}
