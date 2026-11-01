import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { App } from './App'
import { detectLanguage, I18nProvider } from './i18n'
import './styles/tokens.css'
import './styles/shell.css'
import './styles.css'
import './styles/legacy-aliases.css'

const root = document.getElementById('root')
if (!root) {
  throw new Error('Root element not found')
}

createRoot(root).render(
  <StrictMode>
    <BrowserRouter>
      <I18nProvider language={detectLanguage()}>
        <App />
      </I18nProvider>
    </BrowserRouter>
  </StrictMode>,
)
