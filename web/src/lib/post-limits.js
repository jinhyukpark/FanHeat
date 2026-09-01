export const MAX_FEATURED_MEDIA_COUNT = 5

export const featuredMediaCount = ({ imageFiles = [], imagePreviews = [], mediaItems = [] } = {}) =>
  Math.max(imageFiles.length, imagePreviews.length) + mediaItems.length

export function assertFeaturedMediaLimit(payload) {
  if (featuredMediaCount(payload) > MAX_FEATURED_MEDIA_COUNT) {
    throw new Error(`대표 미디어는 최대 ${MAX_FEATURED_MEDIA_COUNT}개까지 등록할 수 있습니다.`)
  }
}
