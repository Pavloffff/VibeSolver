# frontend/desktop

Electron-обёртка над `frontend/web`: локальный и удалённый режимы работы, экран первичной настройки, упаковка в установщик Windows.

## Разработка

1. Соберите веб-интерфейс:

```
cd frontend/web
npm ci
npm run build
```

2. Запустите десктоп:

```
cd ../desktop
npm ci
npm run dev
```

Для горячей перезагрузки веб-интерфейса поднимите `npm run dev` в `frontend/web` и запустите Electron с переменной окружения `ELECTRON_DEV_URL=http://localhost:5173`.

## Сборка установщика Windows

```
npm run dist:win
```

Артефакт: `release/VibeSolver-Setup-<version>.exe`. Полная сборка проекта (тесты backend и frontend + установщик) — корневым скриптом `build-windows.ps1`.

## Конфигурация

`%APPDATA%/vibesolver-desktop/config.json`:

```json
{ "mode": "local", "serverUrl": "http://localhost:8000" }
```

- `local` — запуск всех сервисов через `docker compose` (файлы `compose.yml` и `.env` из корня репозитория; Docker Desktop должен быть установлен и запущен);
- `remote` — подключение к внешнему серверу по указанному адресу.

Изменить режим можно в любой момент: страница «Настройки» в приложении вызывает `window.vibesolver.openSettings()`, и экран первичной настройки открывается снова.
