import { contextBridge, ipcRenderer } from 'electron';
import type { HealthCheckResult, SaveConfigResult, VibesolverBridge, VibesolverConfig } from './bridge-types';

function readFlag(name: string): string | null {
  const prefix = `--${name}=`;
  for (const argument of process.argv) {
    if (argument.startsWith(prefix)) {
      return argument.slice(prefix.length);
    }
  }
  return null;
}

const apiUrl = readFlag('vs-api-url');
if (apiUrl !== null) {
  contextBridge.exposeInMainWorld('__VIBESOLVER_API_URL__', apiUrl);
}

contextBridge.exposeInMainWorld(
  'vibesolver',
  {
    getAppVersion: (): Promise<string> => ipcRenderer.invoke('app:version') as Promise<string>,
    openSettings: (): void => {
      ipcRenderer.send('settings:open');
    },
    getConfig: (): Promise<VibesolverConfig | null> =>
      ipcRenderer.invoke('config:get') as Promise<VibesolverConfig | null>,
    saveConfig: (config: VibesolverConfig): Promise<SaveConfigResult> =>
      ipcRenderer.invoke('config:save', config) as Promise<SaveConfigResult>,
    checkHealth: (serverUrl: string): Promise<HealthCheckResult> =>
      ipcRenderer.invoke('health:check', serverUrl) as Promise<HealthCheckResult>,
  } satisfies VibesolverBridge
);
