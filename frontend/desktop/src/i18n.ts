export type Lang = 'en' | 'ru' | 'zh';

export const LANGS: readonly Lang[] = ['en', 'ru', 'zh'];

export const DEFAULT_LANG: Lang = 'en';

export function isLang(value: unknown): value is Lang {
  return typeof value === 'string' && (LANGS as readonly string[]).includes(value);
}

const en = {
  'dockerMissing.title': 'Docker not found',
  'dockerMissing.body':
    'Install Docker Desktop (https://www.docker.com/products/docker-desktop/), start it, and launch the application again.',
  'envMissing.title': 'Local environment not found',
  'envMissing.body':
    'Files required for local startup were not found:\n{compose}\n{env}\n\nYou can connect to an external server via settings.',
  'healthTimeout.title': 'Server did not respond',
  'healthTimeout.body':
    'The VibeSolver server at {url} did not respond within {seconds} seconds. Check that Docker is running and try again.',
  'healthTimeout.continue': 'Continue anyway',
  'healthTimeout.settings': 'Open settings',
  'healthTimeout.quit': 'Quit',
  'invalidUrl': 'Enter a valid server address (for example, http://host:8000).',
  'invalidConfig': 'Invalid connection settings.',
  'restartError.title': 'Startup error',
  'restartError.body': 'Failed to restart the application: {error}',
  'launchError.title': 'Startup error',
  'launchError.body': 'Failed to start the application: {error}',
  'health.httpError': 'Server responded with an error (HTTP {status}).',
  'health.connectError': 'Could not connect to the server: {error}',
  'health.serverDown': 'Server is not responding.',
  'startup.loading': 'Starting VibeSolver…',
  'startup.loadingHint':
    'Preparing the local environment via Docker. The first launch may take several minutes.',
  'configScreen.title': 'VibeSolver setup',
  'configScreen.subtitle': 'Choose how the application should work.',
  'configScreen.localTitle': 'Local',
  'configScreen.localDesc':
    'All services run on this computer via Docker. No additional setup is required.',
  'configScreen.remoteTitle': 'Connect to server',
  'configScreen.remoteDesc': 'The application connects to an already deployed VibeSolver server.',
  'configScreen.urlLabel': 'Server address',
  'configScreen.checkConnection': 'Check connection',
  'configScreen.start': 'Start',
  'configScreen.langLabel': 'Language',
  'language.en': 'English',
  'language.ru': 'Русский',
  'language.zh': '中文',
  'configScreen.statusChecking': 'Checking connection…',
  'configScreen.statusConnected': 'Connection established.',
  'configScreen.statusSaved': 'Settings saved. Continuing…',
  'configScreen.statusSaveFailed': 'Failed to save settings.',
  'configScreen.bridgeError': 'Error: application bridge is unavailable.',
} as const;

export type TranslationKey = keyof typeof en;

type Dictionary = Record<TranslationKey, string>;

const ru: Dictionary = {
  'dockerMissing.title': 'Docker не найден',
  'dockerMissing.body':
    'Установите Docker Desktop (https://www.docker.com/products/docker-desktop/), запустите его и повторно откройте приложение.',
  'envMissing.title': 'Локальное окружение не найдено',
  'envMissing.body':
    'Не найдены файлы, необходимые для локального запуска:\n{compose}\n{env}\n\nМожно подключиться к внешнему серверу через настройки.',
  'healthTimeout.title': 'Сервер не ответил',
  'healthTimeout.body':
    'Сервер VibeSolver по адресу {url} не ответил за {seconds} секунд. Проверьте, что Docker запущен, и попробуйте снова.',
  'healthTimeout.continue': 'Продолжить всё равно',
  'healthTimeout.settings': 'Открыть настройки',
  'healthTimeout.quit': 'Выйти',
  'invalidUrl': 'Введите корректный адрес сервера (например, http://[IP-АДРЕС]:8000).',
  'invalidConfig': 'Некорректные настройки подключения.',
  'restartError.title': 'Ошибка запуска',
  'restartError.body': 'Не удалось перезапустить приложение: {error}',
  'launchError.title': 'Ошибка запуска',
  'launchError.body': 'Не удалось запустить приложение: {error}',
  'health.httpError': 'Сервер ответил ошибкой (HTTP {status}).',
  'health.connectError': 'Не удалось подключиться к серверу: {error}',
  'health.serverDown': 'Сервер не отвечает.',
  'startup.loading': 'Запускаем VibeSolver…',
  'startup.loadingHint': 'Готовим локальное окружение через Docker. Первый запуск может занять несколько минут.',
  'configScreen.title': 'Настройка VibeSolver',
  'configScreen.subtitle': 'Выберите режим работы приложения.',
  'configScreen.localTitle': 'Локально',
  'configScreen.localDesc':
    'Все сервисы запускаются на этом компьютере через Docker. Ничего дополнительно настраивать не нужно.',
  'configScreen.remoteTitle': 'Подключиться к серверу',
  'configScreen.remoteDesc': 'Приложение подключится к уже развёрнутому серверу VibeSolver.',
  'configScreen.urlLabel': 'Адрес сервера',
  'configScreen.checkConnection': 'Проверить соединение',
  'configScreen.start': 'Начать работу',
  'configScreen.langLabel': 'Язык',
  'language.en': 'English',
  'language.ru': 'Русский',
  'language.zh': '中文',
  'configScreen.statusChecking': 'Проверяем соединение…',
  'configScreen.statusConnected': 'Соединение установлено.',
  'configScreen.statusSaved': 'Настройки сохранены. Продолжаем…',
  'configScreen.statusSaveFailed': 'Не удалось сохранить настройки.',
  'configScreen.bridgeError': 'Ошибка: недоступен мост приложения.',
};

const zh: Dictionary = {
  'dockerMissing.title': '未找到 Docker',
  'dockerMissing.body':
    '请安装 Docker Desktop（https://www.docker.com/products/docker-desktop/），启动后重新运行本应用。',
  'envMissing.title': '未找到本地环境',
  'envMissing.body':
    '未找到本地启动所需的文件：\n{compose}\n{env}\n\n您可以在设置中连接到外部服务器。',
  'healthTimeout.title': '服务器未响应',
  'healthTimeout.body':
    'VibeSolver 服务器（{url}）在 {seconds} 秒内未响应。请检查 Docker 是否正在运行，然后重试。',
  'healthTimeout.continue': '仍然继续',
  'healthTimeout.settings': '打开设置',
  'healthTimeout.quit': '退出',
  'invalidUrl': '请输入正确的服务器地址（例如 http://主机:8000）。',
  'invalidConfig': '连接设置无效。',
  'restartError.title': '启动错误',
  'restartError.body': '无法重新启动应用：{error}',
  'launchError.title': '启动错误',
  'launchError.body': '无法启动应用：{error}',
  'health.httpError': '服务器返回错误（HTTP {status}）。',
  'health.connectError': '无法连接到服务器：{error}',
  'health.serverDown': '服务器无响应。',
  'startup.loading': '正在启动 VibeSolver…',
  'startup.loadingHint': '正在通过 Docker 准备本地环境。首次启动可能需要几分钟。',
  'configScreen.title': 'VibeSolver 设置',
  'configScreen.subtitle': '选择应用的工作模式。',
  'configScreen.localTitle': '本地模式',
  'configScreen.localDesc': '所有服务通过 Docker 在本机运行，无需额外配置。',
  'configScreen.remoteTitle': '连接到服务器',
  'configScreen.remoteDesc': '应用将连接到已部署的 VibeSolver 服务器。',
  'configScreen.urlLabel': '服务器地址',
  'configScreen.checkConnection': '测试连接',
  'configScreen.start': '开始使用',
  'configScreen.langLabel': '语言',
  'language.en': 'English',
  'language.ru': 'Русский',
  'language.zh': '中文',
  'configScreen.statusChecking': '正在检查连接…',
  'configScreen.statusConnected': '连接成功。',
  'configScreen.statusSaved': '设置已保存，正在继续…',
  'configScreen.statusSaveFailed': '保存设置失败。',
  'configScreen.bridgeError': '错误：应用桥接不可用。',
};

const DICTIONARIES: Record<Lang, Dictionary> = { en, ru, zh };

export function t(
  key: TranslationKey,
  lang: Lang,
  params?: Readonly<Record<string, string | number>>
): string {
  const dictionary = DICTIONARIES[lang] ?? DICTIONARIES[DEFAULT_LANG];
  let text = dictionary[key];
  if (params !== undefined) {
    for (const [name, value] of Object.entries(params)) {
      text = text.replaceAll(`{${name}}`, String(value));
    }
  }
  return text;
}
