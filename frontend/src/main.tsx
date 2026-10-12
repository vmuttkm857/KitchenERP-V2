import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from './app/App'
import { AuthProvider } from './auth/AuthContext'
import { installGlobalDiagnostics,startPageObservation } from './monitoring/performanceMonitor'
import './styles/global.css'

installGlobalDiagnostics()
startPageObservation('spa-startup')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
)
