import { useState } from 'react'
import ModeScreen from '../pages/mode-page'
import SettingsPage from '../pages/settings-page'
import SourcesPage from '../pages/sources-page'
import { getApiBaseUrl } from '../shared/config'
import { useT } from '../shared/i18n'
import { getSettings } from '../shared/state/settings'
import type { AppSettings } from '../shared/state/settings'

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
