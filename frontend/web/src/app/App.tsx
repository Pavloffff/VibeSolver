import { useEffect, useState } from 'react'
import ModeScreen from '../pages/mode-page'
import SettingsPage from '../pages/settings-page'
import SourcesPage from '../pages/sources-page'
import ProjectPage from '../pages/project-page'
import IssuesPage from '../pages/issues-page'
import { getApiBaseUrl } from '../shared/config'
import { useT } from '../shared/i18n'
import { getSettings, getTheme, saveTheme } from '../shared/state/settings'
import type { AppSettings, Theme } from '../shared/state/settings'
import type { Source } from '../shared/api/types'

type Tab = 'sources' | 'settings'
type ProjectSection = 'overview' | 'issues'

function tabClass(active: boolean): string {
  return active ? 'side-link side-link-active' : 'side-link'
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
  const [theme, setTheme] = useState<Theme>(() => getTheme())
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null)
  const [selectedProjectName, setSelectedProjectName] = useState<string | null>(null)
  const [projectSection, setProjectSection] = useState<ProjectSection>('overview')
  const [projectLaunchError, setProjectLaunchError] = useState<string | null>(null)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  const updateTheme = (nextTheme: Theme): void => {
    setTheme(nextTheme)
    saveTheme(nextTheme)
  }

  if (settings === null) {
    return <ModeScreen onDone={setSettings} />
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">V</span>
          <span>VibeSolver</span>
        </div>
        <nav className="side-nav" aria-label={t('app.navigation')}>
          <button
            type="button"
            className={tabClass(tab === 'sources')}
            onClick={() => {
              setTab('sources')
              setSelectedProjectId(null)
              setSelectedProjectName(null)
              setProjectSection('overview')
              setProjectLaunchError(null)
            }}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H10v6H4V5.5ZM4 12h6v8H5.5A1.5 1.5 0 0 1 4 18.5V12Zm8-8h6.5A1.5 1.5 0 0 1 20 5.5V10h-8V4Zm0 8h8v6.5a1.5 1.5 0 0 1-1.5 1.5H12v-8Z" /></svg>
            {t('common.sources')}
          </button>
          <button
            type="button"
            className={tabClass(tab === 'settings')}
            onClick={() => {
              setTab('settings')
            }}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 8.25a3.75 3.75 0 1 0 0 7.5 3.75 3.75 0 0 0 0-7.5Zm9 4.57v-1.64l-2.14-.73a7.11 7.11 0 0 0-.65-1.56l1-2.03-1.16-1.16-2.03 1a7.11 7.11 0 0 0-1.56-.65L13.73 3.9h-1.64l-.73 2.14a7.11 7.11 0 0 0-1.56.65l-2.03-1L6.61 6.85l1 2.03a7.11 7.11 0 0 0-.65 1.56l-2.14.73v1.64l2.14.73c.14.55.36 1.07.65 1.56l-1 2.03 1.16 1.16 2.03-1c.49.29 1.01.51 1.56.65l.73 2.14h1.64l.73-2.14c.55-.14 1.07-.36 1.56-.65l2.03 1 1.16-1.16-1-2.03c.29-.49.51-1.01.65-1.56L21 12.82Z" /></svg>
            {t('common.settings')}
          </button>
        </nav>
        <div className="sidebar-footer">
          <button
            type="button"
            className="theme-toggle"
            onClick={() => updateTheme(theme === 'light' ? 'dark' : 'light')}
            aria-label={t(theme === 'light' ? 'settings.themeDark' : 'settings.themeLight')}
            title={t(theme === 'light' ? 'settings.themeDark' : 'settings.themeLight')}
          >
            {theme === 'light' ? (
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.2 15.2A8.1 8.1 0 0 1 8.8 3.8 8.25 8.25 0 1 0 20.2 15.2Z" /></svg>
            ) : (
              <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3.5" /><path d="M12 2.5v2m0 15v2m9.5-9.5h-2m-15 0h-2m16.22-6.72-1.42 1.42M6.7 17.3l-1.42 1.42m13.44 0-1.42-1.42M6.7 6.7 5.28 5.28" /></svg>
            )}
            <span>{t(theme === 'light' ? 'settings.themeDark' : 'settings.themeLight')}</span>
          </button>
          <div className="sidebar-caption">{t('app.workspace')}</div>
        </div>
      </aside>
      <main className="main-panel">
        <div className="topbar">
          <div className="breadcrumb">
            <button type="button" className="breadcrumb-link" onClick={() => { setTab('sources'); setSelectedProjectId(null); setSelectedProjectName(null); setProjectSection('overview'); setProjectLaunchError(null) }}>{t('app.workspace')}</button>
            {tab === 'settings' ? <><span className="breadcrumb-separator">/</span><strong>{t('common.settings')}</strong></> : <>
              {selectedProjectId !== null && <><span className="breadcrumb-separator">/</span><button type="button" className="breadcrumb-link" onClick={() => { setSelectedProjectId(null); setSelectedProjectName(null); setProjectSection('overview'); setProjectLaunchError(null) }}>{t('common.sources')}</button><span className="breadcrumb-separator">/</span>{projectSection === 'issues' ? <><button type="button" className="breadcrumb-link" onClick={() => setProjectSection('overview')}>{selectedProjectName ?? t('project.title')}</button><span className="breadcrumb-separator">/</span><strong>{t('project.issues')}</strong></> : <strong>{selectedProjectName ?? t('project.title')}</strong>}</>}
              {selectedProjectId === null && <><span className="breadcrumb-separator">/</span><strong>{t('common.sources')}</strong></>}
            </>}
          </div>
          <span className="topbar-context">{t(settings.mode === 'local' ? 'common.local' : 'common.remote')}</span>
        </div>
        <div className="content">
        {tab === 'sources' ? (
          selectedProjectId === null ? (
            <SourcesPage
              onProjectSelected={(id) => { setProjectLaunchError(null); setSelectedProjectName(null); setProjectSection('overview'); setSelectedProjectId(id) }}
              onProjectCreated={(source: Source, importError) => { setProjectLaunchError(importError ?? null); setSelectedProjectName(source.name); setProjectSection('overview'); setSelectedProjectId(source.id) }}
            />
          ) : (
            projectSection === 'issues' ? (
              <IssuesPage projectName={selectedProjectName ?? t('project.title')} />
            ) : (
              <ProjectPage key={selectedProjectId} sourceId={selectedProjectId} launchError={projectLaunchError} onNameChange={setSelectedProjectName} onOpenIssues={() => setProjectSection('issues')} onBack={() => { setSelectedProjectId(null); setSelectedProjectName(null); setProjectSection('overview'); setProjectLaunchError(null) }} />
            )
          )
        ) : (
          <SettingsPage
            theme={theme}
            onThemeChange={updateTheme}
            onSaved={() => {
              setSettings(getSettings())
            }}
          />
        )}
        </div>
      </main>
    </div>
  )
}
