import { useState } from 'react'
import ModeScreen from './components/ModeScreen'
import SettingsPage from './components/SettingsPage'
import SourcesPage from './components/SourcesPage'
import { getApiBaseUrl } from './config'
import { useT } from './i18n'
import { getSettings } from './state/settings'
import type { AppSettings } from './state/settings'

type Tab = 'sources' | 'settings'

function tabClass(active: boolean): string {
  return active ? 'tab tab-active' : 'tab'
}

function isDesktopBridgePresent(): boolean {
  return typeof window !== 'undefined' && window.vibesolver !== undefined
}

export default function App() {
  const { t } = useT()
  const [settings, setSettings] = useState<AppSettings | null>(() =>
    isDesktopBridgePresent() ? { mode: 'local', serverUrl: getApiBaseUrl() } : getSettings(),
  )
  const [tab, setTab] = useState<Tab>('sources')

  if (settings === null) {
    return <ModeScreen onDone={setSettings} />
  }

  return (
    <div className="app">
      <header className="header">
        <h1>VibeSolver</h1>
        <nav className="tabs">
          <button
            type="button"
            className={tabClass(tab === 'sources')}
            onClick={() => {
              setTab('sources')
            }}
          >
            {t('common.sources')}
          </button>
          <button
            type="button"
            className={tabClass(tab === 'settings')}
            onClick={() => {
              setTab('settings')
            }}
          >
            {t('common.settings')}
          </button>
        </nav>
      </header>
      <main className="content">
        {tab === 'sources' ? (
          <SourcesPage />
        ) : (
          <SettingsPage
            onSaved={() => {
              setSettings(getSettings())
            }}
          />
        )}
      </main>
    </div>
  )
}
