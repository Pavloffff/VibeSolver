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
  getAppVersion(): Promise<string>;
  openSettings(): void;
  getConfig(): Promise<VibesolverConfig | null>;
  saveConfig(config: VibesolverConfig): Promise<SaveConfigResult>;
  checkHealth(serverUrl: string): Promise<HealthCheckResult>;
}
