import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './styles.css'
import './mobile-pwa.css'
import './feed-overlay-scroll.css'
import './admin.css'
import './my-page-readable.css'

createRoot(document.getElementById('root')).render(
  <StrictMode><App /></StrictMode>,
)

if ('serviceWorker' in navigator) {
  if (import.meta.env.PROD) {
    window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}))
  } else {
    navigator.serviceWorker.getRegistrations().then(registrations => registrations.forEach(registration => registration.unregister()))
    if ('caches' in window) caches.keys().then(keys => keys.filter(key => key.startsWith('fanheat-shell-')).forEach(key => caches.delete(key)))
  }
}
