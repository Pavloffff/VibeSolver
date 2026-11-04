import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { I18nProvider, t } from './i18n'
import { getLang } from './state/settings'
import './styles.css'

const rootElement = document.getElementById('root')
if (rootElement === null) {
  throw new Error(t(getLang(), 'errors.rootElementMissing'))
}

createRoot(rootElement).render(
  <StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </StrictMode>,
)
