import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'

const SITE_URL = 'https://fanheat.io'
const xmlEscape = value => String(value ?? '').replace(/[<>&'\"]/g, character => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;' })[character])
const htmlEscape = value => String(value ?? '').replace(/[<>&'\"]/g, character => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&#39;', '"': '&quot;' })[character])
const absoluteUrl = value => { try { return new URL(value || '/images/auth-concert.jpg', SITE_URL).href } catch { return `${SITE_URL}/images/auth-concert.jpg` } }
const replaceMeta = (html, attribute, name, content) => html.replace(new RegExp(`<meta ${attribute}="${name}" content="[^"]*" \\/>`), `<meta ${attribute}="${name}" content="${htmlEscape(content)}" />`)

const seoPagesPlugin = env => {
  let posts = []
  let outDir = ''
  return {
    name: 'fanheat-public-post-seo',
    configResolved(config) { outDir = config.build.outDir },
    async buildStart() {
      if (!env.VITE_SUPABASE_URL || !env.VITE_SUPABASE_PUBLISHABLE_KEY) return
      try {
        const select = 'id,title,summary,tags,author_display_name,published_at,created_at,post_images(image_url,sort_order)'
        const response = await fetch(`${env.VITE_SUPABASE_URL}/rest/v1/posts?select=${encodeURIComponent(select)}&status=eq.published&order=published_at.desc`, { headers: { apikey: env.VITE_SUPABASE_PUBLISHABLE_KEY } })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        posts = await response.json()
      } catch (error) { this.warn(`공개 게시글 SEO 페이지를 불러오지 못했습니다: ${error.message}`) }
    },
    async writeBundle() {
      const home = await readFile(join(outDir, 'index.html'), 'utf8')
      const urls = [{ loc: `${SITE_URL}/`, lastmod: new Date().toISOString() }]
      for (const post of posts) {
        const canonical = `${SITE_URL}/posts/${post.id}`
        const title = `${post.title} | FANHEAT K-POP 팬 콘텐츠`
        const description = post.summary || `${post.title}에 관한 K-POP 팬 콘텐츠와 이야기를 확인하세요.`
        const tags = Array.isArray(post.tags) ? post.tags.map(tag => String(tag).replace(/^#+/, '').trim()).filter(Boolean) : []
        const image = absoluteUrl([...(post.post_images || [])].sort((a, b) => a.sort_order - b.sort_order)[0]?.image_url)
        const published = post.published_at || post.created_at
        const schema = { '@context': 'https://schema.org', '@type': 'Article', headline: post.title, description, image: [image], keywords: tags, inLanguage: 'ko-KR', author: { '@type': 'Person', name: post.author_display_name || 'FANHEAT Fan' }, publisher: { '@type': 'Organization', name: 'FANHEAT', logo: { '@type': 'ImageObject', url: `${SITE_URL}/images/fanheat-logo.png` } }, mainEntityOfPage: canonical, datePublished: published, dateModified: published }
        let page = home.replace(/<title>[^<]*<\/title>/, `<title>${htmlEscape(title)}</title>`)
        page = replaceMeta(page, 'name', 'description', description)
        page = replaceMeta(page, 'name', 'keywords', [...tags, 'K-POP', '팬 커뮤니티', 'FANHEAT'].join(', '))
        for (const [name, value] of [['og:type', 'article'], ['og:title', title], ['og:description', description], ['og:image', image]]) page = replaceMeta(page, 'property', name, value)
        for (const [name, value] of [['twitter:title', title], ['twitter:description', description], ['twitter:image', image]]) page = replaceMeta(page, 'name', name, value)
        page = page.replace('</head>', `    <link rel="canonical" href="${canonical}" />\n    <meta property="og:url" content="${canonical}" />\n    <meta property="article:published_time" content="${htmlEscape(published)}" />\n    <script id="fanheat-structured-data" type="application/ld+json">${JSON.stringify(schema).replace(/</g, '\\u003c')}</script>\n  </head>`)
        page = page.replace('<div id="root"></div>', `<div id="root"></div><noscript><article><h1>${htmlEscape(post.title)}</h1><p>${htmlEscape(description)}</p>${tags.length ? `<p>${tags.map(tag => `#${htmlEscape(tag)}`).join(' ')}</p>` : ''}<a href="${canonical}">FANHEAT에서 게시글 보기</a></article></noscript>`)
        const postDirectory = join(outDir, 'posts', post.id)
        await mkdir(postDirectory, { recursive: true })
        await writeFile(join(postDirectory, 'index.html'), page)
        urls.push({ loc: canonical, lastmod: published })
      }
      await writeFile(join(outDir, 'sitemap.xml'), `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.map(({ loc, lastmod }) => `  <url><loc>${xmlEscape(loc)}</loc><lastmod>${xmlEscape(lastmod)}</lastmod></url>`).join('\n')}\n</urlset>\n`)
    },
  }
}

export default defineConfig(({ mode }) => {
  const buildId = new Date().toISOString()
  const env = { ...loadEnv(mode, process.cwd(), ''), ...process.env }
  return {
    define: { __FANHEAT_BUILD_ID__: JSON.stringify(buildId) },
    plugins: [
      react(),
      seoPagesPlugin(env),
      { name: 'fanheat-build-version', generateBundle() { this.emitFile({ type: 'asset', fileName: 'version.json', source: JSON.stringify({ buildId }) }) } },
    ],
  }
})
