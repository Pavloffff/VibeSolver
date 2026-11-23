import type { en } from './en'

export type Lang = 'en' | 'ru' | 'zh'

export type TranslationKey = keyof typeof en
export type Dict = Record<TranslationKey, string>
