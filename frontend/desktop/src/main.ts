import { app, BrowserWindow, dialog, ipcMain, protocol } from 'electron';
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { DEFAULT_LANG, t, type Lang } from './i18n';
import {
  normalizeServerUrl,
  parseConfigValue,
  readConfig,
  resolveServerUrl,
  writeConfig,
} from './config';
import type { HealthCheckResult, SaveConfigResult, VibesolverConfig } from './bridge-types';

const APP_SCHEME = 'vsapp';
const APP_HOST = 'app';
const DEFAULT_HEALTH_POLL_INTERVAL_MS = 3000;
const DEFAULT_HEALTH_TOTAL_TIMEOUT_MS = 180000;
const DEFAULT_HEALTH_REQUEST_TIMEOUT_MS = 4000;
const RESTART_DELAY_MS = 400;

function envInt(name: string, fallback: number): number {
  const parsed = Number.parseInt(process.env[name] ?? '', 10);
  return Number.isNaN(parsed) ? fallback : parsed;
}

const HEALTH_POLL_INTERVAL_MS = envInt('VIBESOLVER_HEALTH_POLL_INTERVAL_MS', DEFAULT_HEALTH_POLL_INTERVAL_MS);
const HEALTH_TOTAL_TIMEOUT_MS = envInt('VIBESOLVER_HEALTH_TIMEOUT_MS', DEFAULT_HEALTH_TOTAL_TIMEOUT_MS);
const HEALTH_REQUEST_TIMEOUT_MS = envInt('VIBESOLVER_HEALTH_REQUEST_TIMEOUT_MS', DEFAULT_HEALTH_REQUEST_TIMEOUT_MS);

type StartupDecision = 'continue-anyway' | 'open-settings' | 'quit';
type LocalPreparationResult = StartupDecision | 'continue';

protocol.registerSchemesAsPrivileged([
  { scheme: APP_SCHEME, privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true } },
]);

let mainWindow: BrowserWindow | null = null;

function currentLang(): Lang {
  return readConfig()?.lang ?? DEFAULT_LANG;
}

function repoRoot(): string {
  if (!app.isPackaged) {
    return path.resolve(__dirname, '..', '..', '..');
  }
  const override = process.env.VIBESOLVER_REPO_ROOT;
  if (override !== undefined && override.trim().length > 0) {
    return path.resolve(override);
  }
  const fromCompose = findDirectoryUpward(app.getAppPath(), 'docker-compose.yml');
  if (fromCompose !== null) {
    return fromCompose;
  }
  return app.getAppPath();
}

function findDirectoryUpward(start: string, fileName: string): string | null {
  let directory = path.resolve(start);
  for (;;) {
    if (fs.existsSync(path.join(directory, fileName))) {
      return directory;
    }
    const parent = path.dirname(directory);
    if (parent === directory) {
      return null;
    }
    directory = parent;
  }
}

function webRootDir(): string {
  if (app.isPackaged) {
    return path.join(app.getAppPath(), 'web-dist');
  }
  return path.join(repoRoot(), 'frontend', 'web', 'dist');
}

function contentTypeFor(filePath: string): string {
  const extension = path.extname(filePath).toLowerCase();
  switch (extension) {
    case '.html':
      return 'text/html; charset=utf-8';
    case '.js':
    case '.mjs':
      return 'text/javascript; charset=utf-8';
    case '.css':
      return 'text/css; charset=utf-8';
    case '.json':
    case '.map':
      return 'application/json; charset=utf-8';
    case '.svg':
      return 'image/svg+xml';
    case '.png':
      return 'image/png';
    case '.jpg':
    case '.jpeg':
      return 'image/jpeg';
    case '.gif':
      return 'image/gif';
    case '.ico':
      return 'image/x-icon';
    case '.woff':
      return 'font/woff';
    case '.woff2':
      return 'font/woff2';
    case '.txt':
      return 'text/plain; charset=utf-8';
    default:
      return 'application/octet-stream';
  }
}

function registerAppProtocol(): void {
  const root = webRootDir();
  protocol.handle(APP_SCHEME, async (request): Promise<Response> => {
    const url = new URL(request.url);
    const relativePath =
      url.pathname === '/' ? 'index.html' : decodeURIComponent(url.pathname.replace(/^\/+/, ''));
    const target = path.normalize(path.join(root, relativePath));
    if (target !== root && !target.startsWith(`${root}${path.sep}`)) {
      return new Response('Not found', { status: 404 });
    }
    let stats: fs.Stats | null = null;
    try {
      stats = fs.statSync(target);
    } catch {
      stats = null;
    }
    if (stats === null || !stats.isFile()) {
      return new Response('Not found', { status: 404 });
    }
    const body = await fs.promises.readFile(target);
    return new Response(new Uint8Array(body), { headers: { 'Content-Type': contentTypeFor(target) } });
  });
}

function createWindow(apiUrl: string): BrowserWindow {
  const window = new BrowserWindow({
    width: 1200,
    height: 800,
    title: 'VibeSolver',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      additionalArguments: [
        ...(apiUrl.length > 0 ? [`--vs-api-url=${apiUrl}`] : []),
      ],
    },
  });
  window.once('ready-to-show', () => {
    window.show();
  });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('dom-ready', () => {
    if (apiUrl.length > 0 && !window.isDestroyed()) {
      void window.webContents.executeJavaScript(
        `window.__VIBESOLVER_API_URL__=${JSON.stringify(apiUrl)}; undefined`
      );
    }
  });
  return window;
}

function setMainWindow(window: BrowserWindow): void {
  mainWindow = window;
  window.on('closed', () => {
    if (mainWindow === window) {
      mainWindow = null;
    }
  });
}

function showConfigScreen(window: BrowserWindow): void {
  void window.loadFile(path.join(__dirname, 'config.html'));
}

function loadWebApp(window: BrowserWindow): void {
  const devUrl = process.env.ELECTRON_DEV_URL;
  if (devUrl !== undefined && devUrl.trim().length > 0) {
    void window.loadURL(devUrl.trim());
    return;
  }
  void window.loadURL(`${APP_SCHEME}://${APP_HOST}/index.html`);
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function showStartupScreen(window: BrowserWindow, lang: Lang): void {
  const page = `<!doctype html>
<html lang="${lang}">
<head>
<meta charset="utf-8" />
<title>VibeSolver</title>
<style>
body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; background: #f3f4f6; color: #111827; margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
.card { text-align: center; }
.spinner { width: 36px; height: 36px; border: 4px solid #dbeafe; border-top-color: #2563eb; border-radius: 50%; margin: 0 auto 24px; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
h1 { font-size: 20px; font-weight: 600; margin: 0 0 12px; }
p { color: #6b7280; margin: 0; }
</style>
</head>
<body>
<div class="card">
<div class="spinner"></div>
<h1>${escapeHtml(t('startup.loading', lang))}</h1>
<p>${escapeHtml(t('startup.loadingHint', lang))}</p>
</div>
</body>
</html>`;
  void window.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(page)}`);
}

function dockerAvailable(): boolean {
  try {
    const result = spawnSync('docker', ['--version'], { encoding: 'utf8', windowsHide: true, timeout: 15000 });
    return result.status === 0;
  } catch {
    return false;
  }
}

async function checkHealth(serverUrl: string, lang: Lang): Promise<HealthCheckResult> {
  try {
    const response = await fetch(`${serverUrl}/health`, {
      signal: AbortSignal.timeout(HEALTH_REQUEST_TIMEOUT_MS),
    });
    if (response.ok) {
      return { ok: true };
    }
    return { ok: false, error: t('health.httpError', lang, { status: response.status }) };
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    return { ok: false, error: t('health.connectError', lang, { error: detail }) };
  }
}

async function waitForHealth(serverUrl: string, lang: Lang, window: BrowserWindow): Promise<boolean> {
  const deadline = Date.now() + HEALTH_TOTAL_TIMEOUT_MS;
  while (Date.now() < deadline && !window.isDestroyed()) {
    const result = await checkHealth(serverUrl, lang);
    if (result.ok) {
      return true;
    }
    await sleep(HEALTH_POLL_INTERVAL_MS);
  }
  return false;
}

function askOpenSettings(
  window: BrowserWindow,
  lang: Lang,
  title: string,
  message: string,
  detail: string,
  withContinueAnyway: boolean
): StartupDecision {
  const buttons = withContinueAnyway
    ? [t('healthTimeout.continue', lang), t('healthTimeout.settings', lang), t('healthTimeout.quit', lang)]
    : [t('healthTimeout.settings', lang), t('healthTimeout.quit', lang)];
  const choice = dialog.showMessageBoxSync(window, {
    type: 'error',
    title,
    message,
    detail,
    buttons,
    defaultId: 0,
    cancelId: buttons.length - 1,
  });
  if (withContinueAnyway) {
    if (choice === 0) {
      return 'continue-anyway';
    }
    return choice === 1 ? 'open-settings' : 'quit';
  }
  return choice === 0 ? 'open-settings' : 'quit';
}

function prepareLocalEnvironment(window: BrowserWindow, lang: Lang): LocalPreparationResult {
  if (!dockerAvailable()) {
    dialog.showErrorBox(t('dockerMissing.title', lang), t('dockerMissing.body', lang));
    return 'quit';
  }
  const root = repoRoot();
  const composePath = path.join(root, 'docker-compose.yml');
  const envPath = path.join(root, '.env');
  if (!fs.existsSync(composePath) || !fs.existsSync(envPath)) {
    return askOpenSettings(
      window,
      lang,
      t('envMissing.title', lang),
      t('envMissing.body', lang, { compose: composePath, env: envPath }),
      '',
      false
    );
  }
  try {
    const child = spawn(
      'docker',
      ['compose', '-f', composePath, '--env-file', envPath, 'up', '-d', '--build'],
      { detached: true, stdio: 'ignore', shell: false, windowsHide: true }
    );
    child.unref();
  } catch {
    dialog.showErrorBox(t('dockerMissing.title', lang), t('dockerMissing.body', lang));
    return 'quit';
  }
  return 'continue';
}

async function runStartupFlow(config: VibesolverConfig, window: BrowserWindow): Promise<void> {
  const serverUrl = resolveServerUrl(config);
  if (serverUrl === null) {
    showConfigScreen(window);
    return;
  }
  if (config.mode === 'local') {
    const preparation = prepareLocalEnvironment(window, config.lang);
    if (preparation === 'quit') {
      window.destroy();
      app.quit();
      return;
    }
    if (preparation === 'open-settings') {
      showConfigScreen(window);
      return;
    }
    showStartupScreen(window, config.lang);
    const healthy = await waitForHealth(serverUrl, config.lang, window);
    if (window.isDestroyed()) {
      return;
    }
    if (!healthy) {
      const decision = askOpenSettings(
        window,
        config.lang,
        t('healthTimeout.title', config.lang),
        t('healthTimeout.body', config.lang, {
          url: serverUrl,
          seconds: HEALTH_TOTAL_TIMEOUT_MS / 1000,
        }),
        '',
        true
      );
      if (decision === 'open-settings') {
        showConfigScreen(window);
        return;
      }
      if (decision === 'quit') {
        window.destroy();
        app.quit();
        return;
      }
    }
  }
  loadWebApp(window);
}


async function restartWithConfig(config: VibesolverConfig): Promise<void> {
  await sleep(RESTART_DELAY_MS);
  const previous = mainWindow;
  const serverUrl = resolveServerUrl(config);
  const window = createWindow(serverUrl ?? '');
  setMainWindow(window);
  if (previous !== null && !previous.isDestroyed()) {
    previous.destroy();
  }
  await runStartupFlow(config, window);
}

function registerIpcHandlers(): void {
  ipcMain.handle('app:version', () => app.getVersion());

  ipcMain.handle('config:get', () => readConfig());

  ipcMain.handle('config:save', (_event, value: unknown): SaveConfigResult => {
    const lang = currentLang();
    const config = parseConfigValue(value);
    if (config === null) {
      return { ok: false, error: t('invalidConfig', lang) };
    }
    const serverUrl = resolveServerUrl(config);
    if (serverUrl === null) {
      return { ok: false, error: t('invalidUrl', lang) };
    }
    const normalized: VibesolverConfig = { mode: config.mode, serverUrl, lang: config.lang };
    writeConfig(normalized);
    setImmediate(() => {
      restartWithConfig(normalized).catch((error: unknown) => {
        dialog.showErrorBox(
          t('restartError.title', normalized.lang),
          t('restartError.body', normalized.lang, {
            error: error instanceof Error ? error.message : String(error),
          })
        );
        app.quit();
      });
    });
    return { ok: true };
  });

  ipcMain.handle('health:check', async (_event, value: unknown): Promise<HealthCheckResult> => {
    const lang = currentLang();
    if (typeof value !== 'string') {
      return { ok: false, error: t('invalidUrl', lang) };
    }
    const serverUrl = normalizeServerUrl(value);
    if (serverUrl === null) {
      return { ok: false, error: t('invalidUrl', lang) };
    }
    return checkHealth(serverUrl, lang);
  });

  ipcMain.on('settings:open', (event) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    if (window !== null) {
      showConfigScreen(window);
    }
  });
}

app.on('window-all-closed', () => {
  app.quit();
});

async function launchApplication(): Promise<void> {
  registerIpcHandlers();
  registerAppProtocol();
  const config = readConfig();
  const window = createWindow(config === null ? '' : resolveServerUrl(config) ?? '');
  setMainWindow(window);
  if (config === null) {
    showConfigScreen(window);
    return;
  }
  await runStartupFlow(config, window);
}

void app.whenReady().then(launchApplication).catch((error: unknown) => {
  const lang = DEFAULT_LANG;
  dialog.showErrorBox(
    t('launchError.title', lang),
    t('launchError.body', lang, {
      error: error instanceof Error ? error.message : String(error),
    })
  );
  app.quit();
});
