import { readFileSync } from 'node:fs'

const cssPath = new URL('../src/my-page-readable.css', import.meta.url)
const stylesPath = new URL('../src/styles.css', import.meta.url)
const mainPath = new URL('../src/main.jsx', import.meta.url)
const css = readFileSync(cssPath, 'utf8')
const styles = readFileSync(stylesPath, 'utf8')
const main = readFileSync(mainPath, 'utf8')

const requiredSelectors = [
  '.my-resources article header strong',
  '.my-intro',
  '.my-page-tabs>button',
  '.my-post-list h3',
  '.my-comment-copy q',
  '.friends-tools input',
]

const missing = requiredSelectors.filter(selector => !css.includes(selector))
const undersized = [...css.matchAll(/(?:font-size|font):[^;{}]*?(\d+(?:\.\d+)?)px/g)]
  .map(match => Number(match[1]))
  .filter(size => size > 0 && size < 12)
const fanPhotoStart = styles.lastIndexOf('/* Fan-contributed background photo intake. */')
const fanPhotoCss = fanPhotoStart >= 0 ? styles.slice(fanPhotoStart) : ''
const missingFanPhotoSelectors = ['.fan-photo-modal h2', '.fan-photo-guide>p', '.fan-photo-upload-help', '.fan-photo-consent span']
  .filter(selector => !fanPhotoCss.includes(selector))
const undersizedFanPhoto = [...fanPhotoCss.matchAll(/(?:font-size|font):[^;{}]*?(\d+(?:\.\d+)?)px/g)]
  .map(match => Number(match[1]))
  .filter(size => size > 0 && size < 12)

if (!main.includes("import './my-page-readable.css'")) throw new Error('main.jsx must import my-page-readable.css as the final stylesheet.')
if (missing.length) throw new Error(`Missing protected my-page typography selectors: ${missing.join(', ')}`)
if (undersized.length) throw new Error(`My-page readable layer contains text smaller than 12px: ${undersized.join(', ')}`)
if (missingFanPhotoSelectors.length) throw new Error(`Missing protected fan-photo typography selectors: ${missingFanPhotoSelectors.join(', ')}`)
if (undersizedFanPhoto.length) throw new Error(`Fan-photo modal contains text smaller than 12px: ${undersizedFanPhoto.join(', ')}`)

console.log('My-page and fan-photo typography harness passed: visible text floor is 12px.')
