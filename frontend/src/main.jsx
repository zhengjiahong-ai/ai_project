import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'katex/dist/katex.min.css'
import './index.css'
import App from './App.jsx'
import UnifiedTaskApp from './UnifiedTaskApp.jsx'
import { ToastProvider } from './components/Toast.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ToastProvider>
      {!location.pathname.startsWith('/share/') && new URLSearchParams(location.search).get('unified') !== '0' ? <UnifiedTaskApp /> : <App />}
    </ToastProvider>
  </StrictMode>,
)
