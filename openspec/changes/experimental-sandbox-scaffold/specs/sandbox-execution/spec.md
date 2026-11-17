# Экспериментальная граница sandbox execution

## ADDED Requirements

### Requirement: Sandbox executor по умолчанию выключен

Backend ДОЛЖЕН выключать экспериментальный sandbox execution по умолчанию. Подготовка Docker command plan НЕ ДОЛЖНА исполнять команду или создавать процесс.

#### Scenario: Sandbox отключён

- ДАНО: `VIBESOLVER_EXPERIMENTAL_SANDBOX_ENABLED` отсутствует или равен false
- КОГДА: вызывается построитель execution plan
- ТОГДА: он отклоняет запрос и не запускает Docker/subprocess

### Requirement: Ограниченный Docker plan

При включённой экспериментальной настройке builder ДОЛЖЕН создавать argv без shell interpolation и включать отключённую сеть, запрет неявной загрузки образа, read-only root filesystem, удаление контейнера, непривилегированного пользователя, запрет capabilities, `no-new-privileges`, readonly mount заранее подготовленного snapshot без локальных credentials, изолированный writable workspace и настраиваемые лимиты CPU, RAM, PID и времени. Образ ДОЛЖЕН быть закреплён digest-ом.

#### Scenario: План содержит обязательную изоляцию

- ДАНО: валидная конфигурация и образ `name@sha256:<digest>`
- КОГДА: builder формирует план запуска
- ТОГДА: аргументы включают `--network none`, `--pull=never`, `--read-only`, `--rm`, лимиты ресурсов, readonly snapshot mount и tmpfs workspace

#### Scenario: Плавающий образ или неверные лимиты

- ДАНО: image не закреплён digest-ом либо лимит невалиден
- КОГДА: builder формирует план
- ТОГДА: запрос отклоняется до подготовки команды

### Requirement: Граф обращения не вызывает песочницу

Текущий LangGraph обращений НЕ ДОЛЖЕН вызывать SandboxExecutor или запускать проектные тесты. Подключение возможно отдельным change после реализации runner и проверки межплатформенного lifecycle.

#### Scenario: Обычный запуск issue

- ДАНО: пользователь запускает текущий ticket-agent
- КОГДА: LangGraph исполняет triage, retrieval и resolve
- ТОГДА: sandbox plan не исполняется и код проекта не запускается
