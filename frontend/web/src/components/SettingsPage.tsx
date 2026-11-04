import { useState } from 'react'
import { ApiClient, getErrorMessage } from '../api/client'
import { DEFAULT_SERVER_URL, getApiBaseUrl } from '../config'
import { useT } from '../i18n'
import { LANGS } from '../i18n'
import type { Lang, TranslationKey } from '../i18n'
import { getSettings, saveSettings } from '../state/settings'
import type { AppSettings } from '../state/settings'

type CheckState = 'idle' | 'checking' | 'ok' | 'err'

interface Props {
  onSaved?: () => void
}

const LANGUAGE_LABEL_KEYS: Record<Lang, TranslationKey> = {
  en: 'settings.languageEn',
  ru: 'settings.languageRu',
  zh: 'settings.languageZh',
}

export default function SettingsPage({ onSaved }: Props) {
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

  return (
    <div>
      <h2>{t('common.settings')}</h2>
      <form onSubmit={submit}>
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
          {t('settings.language')}
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
        <button type="submit" className="btn btn-primary">
          {t('common.save')}
        </button>
        {saved && <span className="ok">{t('settings.saved')}</span>}
        {saveError !== null && <span className="error">{saveError}</span>}
      </form>
    </div>
  )
}
