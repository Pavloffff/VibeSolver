import { useState } from 'react'
import { ApiClient, getErrorMessage } from '../../../shared/api/client'
import { DEFAULT_SERVER_URL, getApiBaseUrl } from '../../../shared/config'
import { useT } from '../../../shared/i18n'
import { LANGS } from '../../../shared/i18n'
import type { Lang, TranslationKey } from '../../../shared/i18n'
import { getSettings, saveSettings, saveTheme } from '../../../shared/state/settings'
import type { AppSettings, Theme } from '../../../shared/state/settings'

type CheckState = 'idle' | 'checking' | 'ok' | 'err'

interface Props {
  onSaved?: () => void
  theme?: Theme
  onThemeChange?: (theme: Theme) => void
}

const LANGUAGE_LABEL_KEYS: Record<Lang, TranslationKey> = {
  en: 'settings.languageEn',
  ru: 'settings.languageRu',
  zh: 'settings.languageZh',
}

export default function SettingsPage({ onSaved, theme = 'light', onThemeChange }: Props) {
  const { lang, setLang, t } = useT()
  const [settings, setSettings] = useState<AppSettings>(() => getSettings() ?? { mode: 'local', serverUrl: DEFAULT_SERVER_URL })
  const [checkState, setCheckState] = useState<CheckState>('idle')
  const [checkError, setCheckError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const update = (patch: Partial<AppSettings>) => {
    setSettings((prev) => ({ ...prev, ...patch }))
    setSaved(false)
    setSaveError(null)
  }

  const checkConnection = async () => {
    setCheckState('checking')
    setCheckError(null)
    try {
      await new ApiClient(() => settings.serverUrl).checkHealth()
      setCheckState('ok')
    } catch (error) {
      setCheckError(getErrorMessage(error))
      setCheckState('err')
    }
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    const serverUrl = settings.serverUrl.trim()
    const bridge = typeof window !== 'undefined' ? window.vibesolver : undefined
    if (bridge !== undefined) {
      const result = await bridge.saveConfig({
        mode: settings.mode,
        serverUrl: settings.mode === 'remote' ? serverUrl : getApiBaseUrl(),
        lang,
      })
      if (!result.ok) {
        setSaved(false)
        setSaveError(result.error ?? t('settings.saveFailed'))
        return
      }
    } else {
      saveSettings({ mode: settings.mode, serverUrl })
    }
    setSaved(true)
    setSaveError(null)
    if (onSaved !== undefined) {
      onSaved()
    }
  }

  const changeTheme = (nextTheme: Theme): void => {
    saveTheme(nextTheme)
    onThemeChange?.(nextTheme)
  }

  return (
    <div className="settings-page">
      <div className="settings-heading"><div><span className="eyebrow">{t('app.preferences')}</span><h1>{t('common.settings')}</h1></div><p>{t('settings.description')}</p></div>
      <form onSubmit={submit}>
        <section className="settings-section">
          <div className="settings-section-heading"><div><h2>{t('settings.appearance')}</h2><p>{t('settings.appearanceHint')}</p></div></div>
          <div className="theme-options">
            {(['light', 'dark'] as const).map((option) => (
              <button key={option} type="button" className={`theme-option ${theme === option ? 'theme-option-selected' : ''}`} aria-pressed={theme === option} onClick={() => changeTheme(option)}>
                <span className={`theme-preview theme-preview-${option}`}><i /><i /><i /></span>
                <span>{t(option === 'light' ? 'settings.themeLight' : 'settings.themeDark')}</span>
                {theme === option && <span className="theme-check" aria-hidden="true">✓</span>}
              </button>
            ))}
          </div>
        </section>
        <section className="settings-section">
          <div className="settings-section-heading"><div><h2>{t('settings.connection')}</h2><p>{t('settings.connectionHint')}</p></div></div>
        <label>
          <input
            type="radio"
            name="mode"
            checked={settings.mode === 'local'}
            onChange={() => update({ mode: 'local' })}
          />
          {t('common.local')}
        </label>
        <label>
          <input
            type="radio"
            name="mode"
            checked={settings.mode === 'remote'}
            onChange={() => update({ mode: 'remote' })}
          />
          {t('common.remote')}
        </label>
        <label>
          {t('common.serverUrl')}
          <input
            type="text"
            value={settings.serverUrl}
            onChange={(event) => update({ serverUrl: event.target.value })}
            placeholder="http://localhost:8000"
          />
        </label>
        <div>
          <button
            type="button"
            className="btn"
            disabled={checkState === 'checking'}
            onClick={() => {
              void checkConnection()
            }}
          >
            {t('common.checkConnection')}
          </button>
          {checkState === 'ok' && <span className="ok">{t('common.connectionOk')}</span>}
          {checkState === 'err' && checkError !== null && <span className="error">{checkError}</span>}
        </div>
        </section>
        <section className="settings-section">
          <div className="settings-section-heading"><div><h2>{t('settings.language')}</h2><p>{t('settings.languageHint')}</p></div></div>
          <div className="language-options">
            {LANGS.map((language) => (
              <label key={language}>
                <input
                  type="radio"
                  name="lang"
                  checked={lang === language}
                  onChange={() => {
                    setLang(language)
                  }}
                />
                {t(LANGUAGE_LABEL_KEYS[language])}
              </label>
            ))}
          </div>
        </section>
        <div className="settings-actions">
        <button type="submit" className="btn btn-primary">
          {t('common.save')}
        </button>
        {saved && <span className="ok">{t('settings.saved')}</span>}
        {saveError !== null && <span className="error">{saveError}</span>}
        </div>
      </form>
    </div>
  )
}
