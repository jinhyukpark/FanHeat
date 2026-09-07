const BUILD_ID = typeof __FANHEAT_BUILD_ID__ === 'string' ? __FANHEAT_BUILD_ID__ : 'development'
const CHECK_INTERVAL_MS = 60_000

function showUpdateNotice(registration) {
  if (document.querySelector('.app-update-notice')) return
  const notice = document.createElement('aside')
  notice.className = 'app-update-notice'
  notice.setAttribute('role', 'status')
  notice.setAttribute('aria-live', 'polite')
  notice.innerHTML = '<span><strong>새 버전이 준비됐습니다.</strong><small>업데이트하면 최신 화면과 기능이 적용됩니다.</small></span><button type="button">지금 업데이트</button>'
  notice.querySelector('button').addEventListener('click', async () => {
    const button = notice.querySelector('button')
    button.disabled = true
    button.textContent = '업데이트 중…'
    try {
      await registration?.update()
      registration?.waiting?.postMessage({ type: 'SKIP_WAITING' })
    } finally {
      window.location.reload()
    }
  })
  document.body.append(notice)
}

async function checkBuildVersion(registration) {
  if (document.visibilityState === 'hidden') return
  try {
    const response = await fetch(`/version.json?t=${Date.now()}`, { cache: 'no-store' })
    if (!response.ok) return
    const { buildId } = await response.json()
    if (buildId && buildId !== BUILD_ID) showUpdateNotice(registration)
  } catch {
    // Offline use remains available through the service worker cache.
  }
}

export function registerAppUpdates() {
  if (!('serviceWorker' in navigator)) return
  if (!import.meta.env.PROD) {
    navigator.serviceWorker.getRegistrations().then(registrations => registrations.forEach(registration => registration.unregister()))
    if ('caches' in window) caches.keys().then(keys => keys.filter(key => key.startsWith('fanheat-shell-')).forEach(key => caches.delete(key)))
    return
  }

  window.addEventListener('load', async () => {
    const registration = await navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' }).catch(() => null)
    if (!registration) return
    registration.waiting?.postMessage({ type: 'SKIP_WAITING' })
    registration.addEventListener('updatefound', () => {
      const worker = registration.installing
      worker?.addEventListener('statechange', () => {
        if (worker.state === 'installed' && navigator.serviceWorker.controller) showUpdateNotice(registration)
      })
    })
    const check = () => {
      registration.update().catch(() => {})
      checkBuildVersion(registration)
    }
    window.addEventListener('focus', check)
    window.addEventListener('pageshow', check)
    document.addEventListener('visibilitychange', () => document.visibilityState === 'visible' && check())
    window.setInterval(check, CHECK_INTERVAL_MS)
    check()
  })
}
