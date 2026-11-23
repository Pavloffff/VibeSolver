import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './app/App'
import { I18nProvider, t } from './shared/i18n'
import { getLang, initializeDesktopLanguage } from './shared/state/settings'
import './styles.css'

const rootElement = document.getElementById('root')
if (rootElement === null) {
  throw new Error(t(getLang(), 'errors.rootElementMissing'))
}

const root = createRoot(rootElement)
async function start() {
  const config = await window.vibesolver?.getConfig()
  initializeDesktopLanguage(config?.lang)
  root.render(
    <StrictMode>
      <I18nProvider>
        <App desktopConnection={config ?? undefined} />
      </I18nProvider>
    </StrictMode>,
  )
}
void start()
