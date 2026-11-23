import type { Lang } from '../i18n/types'

export type AppMode = 'local' | 'remote'

export interface AppSettings {
  mode: AppMode
  serverUrl: string
}

export type Theme = 'light' | 'dark'

const SETTINGS_STORAGE_KEY = 'vibesolver.settings'
export const SERVER_URL_STORAGE_KEY = 'vibesolver.serverUrl'
const LANG_STORAGE_KEY = 'vibesolver.lang'
const THEME_STORAGE_KEY = 'vibesolver.theme'
export const EXPERIMENTAL_STORAGE_KEY = 'vibesolver.experimental'

export function getTheme(): Theme {
  return localStorage.getItem(THEME_STORAGE_KEY) === 'dark' ? 'dark' : 'light'
}

export function saveTheme(theme: Theme): void {
  localStorage.setItem(THEME_STORAGE_KEY, theme)
}

export function isExperimentalEnabled(): boolean {
  return localStorage.getItem(EXPERIMENTAL_STORAGE_KEY) === 'true'
}

export function saveExperimentalEnabled(enabled: boolean): void {
  localStorage.setItem(EXPERIMENTAL_STORAGE_KEY, String(enabled))
}

function isLang(value: string): value is Lang {
  return value === 'en' || value === 'ru' || value === 'zh'
}

export function getLang(): Lang {
  const raw = localStorage.getItem(LANG_STORAGE_KEY)
  if (raw !== null && isLang(raw)) {
    return raw
  }
  return 'en'
}

export function saveLang(lang: Lang): void {
  localStorage.setItem(LANG_STORAGE_KEY, lang)
}

export function initializeDesktopLanguage(lang = window.vibesolver?.initialLanguage): void {
  if (typeof lang === 'string' && isLang(lang)) saveLang(lang)
}

export function getSettings(): AppSettings | null {
  const raw = localStorage.getItem(SETTINGS_STORAGE_KEY)
  if (!raw) {
    return null
  }
  try {
    const parsed = JSON.parse(raw) as Partial<AppSettings>
    if (parsed.mode !== 'local' && parsed.mode !== 'remote') {
      return null
    }
    if (typeof parsed.serverUrl !== 'string' || !parsed.serverUrl) {
      return null
    }
    return { mode: parsed.mode, serverUrl: parsed.serverUrl }
  } catch {
    return null
  }
}

export function saveSettings(settings: AppSettings): void {
  localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings))
  localStorage.setItem(SERVER_URL_STORAGE_KEY, settings.serverUrl)
}
