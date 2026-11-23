import type { Lang } from './i18n';

export type AppMode = 'local' | 'remote';

export interface VibesolverConfig {
  mode: AppMode;
  serverUrl: string;
  lang: Lang;
}

export interface HealthCheckResult {
  ok: boolean;
  error?: string;
}

export interface SaveConfigResult {
  ok: boolean;
  error?: string;
}

export interface VibesolverBridge {
  initialLanguage: string | null;
  localServerUrl: string | null;
  getAppVersion(): Promise<string>;
  openSettings(): void;
  openUiObserver(lang?: Lang): Promise<SaveConfigResult>;
  getConfig(): Promise<VibesolverConfig | null>;
  setLanguage(lang: Lang): Promise<SaveConfigResult>;
  saveConfig(config: VibesolverConfig): Promise<SaveConfigResult>;
  checkHealth(serverUrl: string, lang?: Lang): Promise<HealthCheckResult>;
}
