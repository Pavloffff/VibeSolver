import type { Lang } from './i18n/types'
export type BridgeAppMode = 'local' | 'remote'

export interface BridgeConfig {
  mode: BridgeAppMode
  serverUrl: string
  lang: string
}

export interface BridgeResult {
  ok: boolean
  error?: string
}

export interface VibesolverBridge {
  initialLanguage?: string | null
  localServerUrl?: string | null
  getConfig(): Promise<BridgeConfig | null>
  setLanguage(lang: Lang): Promise<BridgeResult>
  saveConfig(config: BridgeConfig): Promise<BridgeResult>
  checkHealth(serverUrl: string): Promise<BridgeResult>
  getAppVersion(): Promise<string>
  openSettings(): void
  openUiObserver?(lang?: Lang): Promise<BridgeResult>
  selectFolder?(): Promise<string | null>
}

declare global {
  interface Window {
    vibesolver?: VibesolverBridge
  }
}

export {}
