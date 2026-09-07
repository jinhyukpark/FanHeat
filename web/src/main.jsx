import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './styles.css'
import './mobile-pwa.css'
import './feed-overlay-scroll.css'
import './admin.css'
import './my-page-readable.css'
import { registerAppUpdates } from './lib/app-updates'

createRoot(document.getElementById('root')).render(
  <StrictMode><App /></StrictMode>,
)

registerAppUpdates()
