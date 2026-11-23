import { useRef, useState } from 'react'
import { ApiClient, getErrorMessage } from '../../../shared/api/client'
import { getLocalServerUrl } from '../../../shared/config'
import { useT } from '../../../shared/i18n'
import { LANGS } from '../../../shared/i18n'
import type { Lang, TranslationKey } from '../../../shared/i18n'
import { getSettings, saveExperimentalEnabled, saveSettings, saveTheme } from '../../../shared/state/settings'
import type { AppSettings, Theme } from '../../../shared/state/settings'
import { isExperimentalEnabled } from '../../../shared/state/settings'

type CheckState = 'idle' | 'checking' | 'ok' | 'err'

interface Props {
  connection?: AppSettings
  onConnectionChange?: (next: AppSettings) => void
  theme?: Theme
  onThemeChange?: (theme: Theme) => void
  experimental?: boolean
  onExperimentalChange?: (enabled: boolean) => void
}

const LANGUAGE_LABEL_KEYS: Record<Lang, TranslationKey> = {
  en: 'settings.languageEn',
  ru: 'settings.languageRu',
  zh: 'settings.languageZh',
}

export default function SettingsPage({ connection, onConnectionChange, theme = 'light', onThemeChange, experimental = isExperimentalEnabled(), onExperimentalChange }: Props) {
  const { lang, setLang, t } = useT()
  const [settings, setSettings] = useState<AppSettings>(() => connection ?? getSettings() ?? { mode: 'local', serverUrl: getLocalServerUrl() })
  const applied = useRef(settings)
  const remoteAddress = useRef(settings.mode === 'remote' ? settings.serverUrl : '')
  const pending = useRef<AppSettings | null>(null)
  const languageChange = useRef(0)
  const checkId = useRef(0)
  const [invalidAddress, setInvalidAddress] = useState(false)
  const [checkState, setCheckState] = useState<CheckState>('idle')
  const [checkError, setCheckError] = useState<unknown>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  const edit = (value: AppSettings) => {
    setSettings(value)
    setInvalidAddress(false)
    setSaveError(null)
    checkId.current++
    setCheckState('idle')
  }

  const checkConnection = async () => {
    const id = ++checkId.current
    setCheckState('checking')
    try {
      await new ApiClient(() => settings.serverUrl).checkHealth()
      if (id === checkId.current) setCheckState('ok')
    } catch (error) {
      if (id === checkId.current) {
        setCheckError(error)
        setCheckState('err')
      }
    }
  }

  const apply = async (draft: AppSettings) => {
    const serverUrl = draft.serverUrl.trim().replace(/\/+$/, '')
    if (!URL.canParse(serverUrl) || !['http:', 'https:'].includes(new URL(serverUrl).protocol)) {
      setInvalidAddress(true)
      return
    }
    const value = { mode: draft.mode, serverUrl }
    const latest = pending.current ?? applied.current
    if (latest.mode === value.mode && latest.serverUrl === serverUrl) return
    pending.current = value
    setSaveError(null)
    try {
      const bridge = window.vibesolver
      if (bridge) {
        const result = await bridge.saveConfig({ ...value, lang })
        if (!result.ok) throw new Error(result.error || t('settings.saveFailed'))
      } else {
        saveSettings(value)
      }
      if (pending.current !== value) return
      applied.current = value
      onConnectionChange?.(value)
    } catch (error) {
      if (pending.current === value) setSaveError(getErrorMessage(error))
    } finally {
      if (pending.current === value) pending.current = null
    }
  }

  const selectMode = (mode: AppSettings['mode']) => {
    const next = { mode, serverUrl: mode === 'local' ? getLocalServerUrl() : remoteAddress.current }
    edit(next)
    if (next.serverUrl) void apply(next)
  }

  const changeLanguage = async (next: Lang) => {
    const id = ++languageChange.current
    setLang(next)
    const bridge = window.vibesolver
    if (!bridge) return
    try {
      const result = await bridge.setLanguage(next)
      if (!result.ok) throw new Error(result.error || t('settings.saveFailed'))
    } catch (error) {
      if (id === languageChange.current) {
        setLang(lang)
        setSaveError(getErrorMessage(error))
      }
    }
  }

  const changeTheme = (nextTheme: Theme): void => {
    saveTheme(nextTheme)
    onThemeChange?.(nextTheme)
  }

  const changeExperimental = (nextEnabled: boolean): void => {
    saveExperimentalEnabled(nextEnabled)
    onExperimentalChange?.(nextEnabled)
  }

  return (
    <div className="settings-page">
      <div className="settings-heading"><div><span className="eyebrow">{t('app.preferences')}</span><h1>{t('common.settings')}</h1></div><p>{t('settings.description')}</p></div>
      <div className="settings-grid">
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
            onChange={() => selectMode('local')}
          />
          {t('common.local')}
        </label>
        <label>
          <input
            type="radio"
            name="mode"
            checked={settings.mode === 'remote'}
            onChange={() => selectMode('remote')}
          />
          {t('common.remote')}
        </label>
        <label>
          {t('common.serverUrl')}
          <input
            type="text"
            value={settings.serverUrl}
            readOnly={settings.mode === 'local'}
            aria-invalid={invalidAddress}
            onChange={event => {
              remoteAddress.current = event.target.value
              edit({ ...settings, serverUrl: event.target.value })
            }}
            onBlur={() => { if (settings.mode === 'remote') void apply(settings) }}
            onKeyDown={event => { if (event.key === 'Enter' && settings.mode === 'remote') void apply(settings) }}
          />
        </label>
        {invalidAddress && <p className="error" role="alert">{t('settings.invalidAddress')}</p>}
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
          {checkState === 'err' && <span className="error">{getErrorMessage(checkError, lang)}</span>}
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
                    void changeLanguage(language)
                  }}
                />
                {t(LANGUAGE_LABEL_KEYS[language])}
              </label>
            ))}
          </div>
        </section>
        <section className="settings-section">
          <div className="settings-section-heading"><div><h2>{t('settings.experimental')}</h2><p>{t('settings.experimentalHint')}</p></div></div>
          <label className="experimental-toggle">
            <input
              type="checkbox"
              checked={experimental}
              onChange={(event) => changeExperimental(event.target.checked)}
            />
            {t('settings.experimentalToggle')}
          </label>
        </section>
        {saveError !== null && <div className="settings-actions error" role="alert">{saveError}</div>}
      </div>
    </div>
  )
}
