import type { en } from './en'

export type Lang = 'en' | 'ru' | 'zh'

export type Dict = typeof en

export type TranslationKey = keyof Dict
