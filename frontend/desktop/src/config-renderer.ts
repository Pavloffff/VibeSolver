import { DEFAULT_LANG, isLang, LANGS, t, type Lang, type TranslationKey } from './i18n';
import type { AppMode, VibesolverConfig } from './bridge-types';

const LANGUAGE_LABEL_KEYS: Record<Lang, TranslationKey> = {
  en: 'language.en',
  ru: 'language.ru',
  zh: 'language.zh',
};

function requireElement<T extends HTMLElement>(id: string, tag?: 'button' | 'input' | 'select'): T {
  const element = document.getElementById(id);
  if (element === null) {
    throw new Error(`Missing UI element: ${id}`);
  }
  if (tag !== undefined && !(element instanceof (tag === 'button' ? HTMLButtonElement : tag === 'input' ? HTMLInputElement : HTMLSelectElement))) {
    throw new Error(`Unexpected element type: ${id}`);
  }
  return element as T;
}

function normalizeServerUrl(raw: string): string | null {
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

function setStatus(element: HTMLElement, text: string, kind: 'ok' | 'error' | 'pending'): void {
  element.textContent = text;
  element.className = `status ${kind}`;
}

function bootstrap(): void {
  const api = window.vibesolver;
  const cardLocal = requireElement<HTMLButtonElement>('card-local', 'button');
  const cardRemote = requireElement<HTMLButtonElement>('card-remote', 'button');
  const langRow = requireElement('lang-row');
  const langSelect = requireElement<HTMLSelectElement>('lang-select', 'select');
  const urlRow = requireElement('url-row');
  const urlInput = requireElement<HTMLInputElement>('server-url', 'input');
  const checkButton = requireElement<HTMLButtonElement>('check-button', 'button');
  const checkStatus = requireElement('check-status');
  const startButton = requireElement<HTMLButtonElement>('start-button', 'button');
  const mainStatus = requireElement('main-status');
  const versionLabel = requireElement('version');

  if (api === undefined) {
    setStatus(mainStatus, t('configScreen.bridgeError', DEFAULT_LANG), 'error');
    return;
  }

  let selectedMode: AppMode = 'local';
  let lang: Lang = DEFAULT_LANG;

  for (const code of LANGS) {
    const option = document.createElement('option');
    option.value = code;
    option.textContent = t(LANGUAGE_LABEL_KEYS[code], lang);
    langSelect.appendChild(option);
  }

  const applyTexts = (): void => {
    document.documentElement.lang = lang;
    requireElement('txt-title').textContent = t('configScreen.title', lang);
    requireElement('txt-subtitle').textContent = t('configScreen.subtitle', lang);
    requireElement('txt-local-title').textContent = t('configScreen.localTitle', lang);
    requireElement('txt-local-desc').textContent = t('configScreen.localDesc', lang);
    requireElement('txt-remote-title').textContent = t('configScreen.remoteTitle', lang);
    requireElement('txt-remote-desc').textContent = t('configScreen.remoteDesc', lang);
    requireElement('txt-url-label').textContent = t('configScreen.urlLabel', lang);
    requireElement('txt-lang-label').textContent = t('configScreen.langLabel', lang);
    urlInput.placeholder = 'http://localhost:8000';
    checkButton.textContent = t('configScreen.checkConnection', lang);
    startButton.textContent = t('configScreen.start', lang);
  };

  const selectMode = (mode: AppMode): void => {
    selectedMode = mode;
    cardLocal.classList.toggle('selected', mode === 'local');
    cardRemote.classList.toggle('selected', mode === 'remote');
    urlRow.hidden = mode !== 'remote';
    if (mode !== 'remote') {
      setStatus(checkStatus, '', 'pending');
    }
  };

  const loadExistingConfig = async (): Promise<void> => {
    const config = await api.getConfig();
    if (config === null) {
      applyTexts();
      return;
    }
    if (isLang(config.lang)) {
      lang = config.lang;
    }
    langSelect.value = lang;
    applyTexts();
    selectMode(config.mode);
    if (config.mode === 'remote') {
      urlInput.value = config.serverUrl;
    }
  };

  const onCheckConnection = async (): Promise<void> => {
    const normalized = normalizeServerUrl(urlInput.value);
    if (normalized === null) {
      setStatus(checkStatus, t('invalidUrl', lang), 'error');
      return;
    }
    checkButton.disabled = true;
    setStatus(checkStatus, t('configScreen.statusChecking', lang), 'pending');
    const result = await api.checkHealth(normalized);
    checkButton.disabled = false;
    if (result.ok) {
      setStatus(checkStatus, t('configScreen.statusConnected', lang), 'ok');
    } else {
      setStatus(checkStatus, result.error ?? t('health.serverDown', lang), 'error');
    }
  };

  const onStart = async (): Promise<void> => {
    let serverUrl = '';
    if (selectedMode === 'remote') {
      const normalized = normalizeServerUrl(urlInput.value);
      if (normalized === null) {
        setStatus(checkStatus, t('invalidUrl', lang), 'error');
        return;
      }
      serverUrl = normalized;
    }
    const config: VibesolverConfig = { mode: selectedMode, serverUrl, lang };
    startButton.disabled = true;
    const result = await api.saveConfig(config);
    if (!result.ok) {
      startButton.disabled = false;
      setStatus(mainStatus, result.error ?? t('configScreen.statusSaveFailed', lang), 'error');
      return;
    }
    setStatus(mainStatus, t('configScreen.statusSaved', lang), 'pending');
  };

  cardLocal.addEventListener('click', () => selectMode('local'));
  cardRemote.addEventListener('click', () => selectMode('remote'));
  langSelect.addEventListener('change', () => {
    const value = langSelect.value;
    if (isLang(value)) {
      lang = value;
      applyTexts();
    }
  });
  checkButton.addEventListener('click', () => void onCheckConnection());
  startButton.addEventListener('click', () => void onStart());
  urlInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      void onCheckConnection();
    }
  });

  langRow.hidden = false;
  applyTexts();
  void api.getAppVersion().then((version) => {
    versionLabel.textContent = `VibeSolver ${version}`;
  });
  void loadExistingConfig();
}

bootstrap();
