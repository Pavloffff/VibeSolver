import { app } from 'electron';
import fs from 'node:fs';
import path from 'node:path';
import { DEFAULT_LANG, isLang } from './i18n';
import type { AppMode, VibesolverConfig } from './bridge-types';

export type { VibesolverConfig };

function configFilePath(): string {
  return path.join(app.getPath('userData'), 'config.json');
}

export function parseConfigValue(value: unknown): VibesolverConfig | null {
  if (typeof value !== 'object' || value === null) {
    return null;
  }
  const record = value as Record<string, unknown>;
  const mode = record['mode'];
  const serverUrl = record['serverUrl'];
  const lang = record['lang'];
  if (mode !== 'local' && mode !== 'remote') {
    return null;
  }
  if (typeof serverUrl !== 'string') {
    return null;
  }
  if (mode === 'remote' && serverUrl.trim().length === 0) {
    return null;
  }
  return {
    mode,
    serverUrl,
    lang: isLang(lang) ? lang : DEFAULT_LANG,
  };
}

export function readConfig(): VibesolverConfig | null {
  try {
    return parseConfigValue(JSON.parse(fs.readFileSync(configFilePath(), 'utf8')));
  } catch {
    return null;
  }
}

export function writeConfig(config: VibesolverConfig): void {
  fs.mkdirSync(app.getPath('userData'), { recursive: true });
  fs.writeFileSync(configFilePath(), `${JSON.stringify(config, null, 2)}\n`, 'utf8');
}

export function normalizeServerUrl(raw: string): string | null {
  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    return null;
  }
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null;
    }
  } catch {
    return null;
  }
  return trimmed.replace(/\/+$/, '');
}

export function localApiUrl(): string {
  return process.env.VIBESOLVER_LOCAL_API ?? 'http://localhost:8000';
}

export function resolveServerUrl(config: VibesolverConfig): string | null {
  if (config.mode === 'local') {
    return localApiUrl();
  }
  return normalizeServerUrl(config.serverUrl);
}

export function isAppMode(value: unknown): value is AppMode {
  return value === 'local' || value === 'remote';
}
