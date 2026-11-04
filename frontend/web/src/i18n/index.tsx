import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { getLang, saveLang } from '../state/settings'
import { en } from './en'
import { ru } from './ru'
import { zh } from './zh'
import type { Dict, Lang, TranslationKey } from './types'

export type { Dict, Lang, TranslationKey }

export const DICTS: Record<Lang, Dict> = { en, ru, zh }

export const LANGS: readonly Lang[] = Object.keys(DICTS) as Lang[]

export function t(lang: Lang, key: TranslationKey, params?: Record<string, string>): string {
  let text: string = DICTS[lang][key]
  if (params !== undefined) {
    for (const [name, value] of Object.entries(params)) {
      text = text.split(`{${name}}`).join(value)
    }
  }
  return text
}

interface I18nContextValue {
  lang: Lang
  setLang: (lang: Lang) => void
  t: (key: TranslationKey, params?: Record<string, string>) => string
}

const I18nContext = createContext<I18nContextValue | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => getLang())

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  const setLang = (next: Lang): void => {
    setLangState(next)
    saveLang(next)
  }

  const value: I18nContextValue = {
    lang,
    setLang,
    t: (key, params) => t(lang, key, params),
  }

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useT(): I18nContextValue {
  const value = useContext(I18nContext)
  if (value === null) {
    throw new Error('I18nProvider is missing')
  }
  return value
}
