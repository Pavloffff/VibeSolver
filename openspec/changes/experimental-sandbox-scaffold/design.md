# Дизайн: заготовка sandbox executor

## Варианты

1. **Сразу выполнять команды через Docker CLI.** Это потребует доступа backend к Docker daemon, корректных bind mounts в Linux/Windows, ограничения stdout, cleanup/timeout handling и тестового lifecycle. В текущем compose такое подключение не настроено.
2. **Сделать контракт и проверяемый command plan без исполнения.** Закладывает безопасные требования и позволяет тестировать аргументы без Docker, но ничего не запускает. Выбор для экспериментальной фазы.
3. **Только документация.** Дешевле, но не формирует программную границу для будущего runner.

## Модель

- `SandboxExecutor` protocol принимает `SandboxExecutionRequest` (путь к заранее подготовленному snapshot без `.env`, `.git` и credentials, плюс argv) и возвращает типизированный результат.
- `DockerSandboxCommandBuilder` проверяет включённый флаг, полный закреплённый image reference, корректность лимитов и строит argv без shell interpolation.
- План задаёт `--network none`, `--pull=never`, `--read-only`, `--rm`, `--cap-drop=ALL`, `no-new-privileges`, непривилегированного UID, ограниченные `--memory`, `--cpus`, `--pids-limit`, readonly mount `/input` и writable tmpfs `/workspace`.
- Вызов генератора command plan не исполняет subprocess. Настройки backend по умолчанию выключены.
- Будущий runner обязан отдельно реализовать timeout, stdout/stderr cap, cross-platform Docker daemon access и удаление временного окружения, прежде чем подключаться к графу.

## Риск

Даже настройки Docker не гарантируют полную защиту от уязвимостей ядра/daemon. Экспериментальная отметка не означает готовность к запуску недоверенного кода в продуктивной среде.
