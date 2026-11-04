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
  getConfig(): Promise<BridgeConfig | null>
  saveConfig(config: BridgeConfig): Promise<BridgeResult>
  checkHealth(serverUrl: string): Promise<BridgeResult>
  getAppVersion(): Promise<string>
  openSettings(): void
  selectFolder?(): Promise<string | null>
}

declare global {
  interface Window {
    vibesolver?: VibesolverBridge
  }
}

export {}
