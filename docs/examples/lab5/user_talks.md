# Lab5. Как опубликовать доклад и найти его в программе

Сервис хранит пользователей, мероприятия и доклады. Докладчик входит в учётную запись, создаёт доклад для существующего мероприятия и проверяет его по идентификатору в программе. Описание сверено с [исходниками lab5 на ревизии 761a40c](https://github.com/Pavloffff/MAI_System_Design/tree/761a40c1f73a8a0c24beb93d88bdc3b67f4a7954/lab5).

## Вход

Отправьте email и пароль зарегистрированного пользователя в `POST /users/login`. При успешной проверке сервис выдаёт токен. Для запросов к докладам передавайте его в заголовке `Authorization: Bearer <token>`. Проверьте результат входа перед следующим запросом. При неизвестном email или неверном пароле сервис возвращает отрицательный результат и пустую строку токена. [Проверка пользователя](https://github.com/Pavloffff/MAI_System_Design/blob/761a40c1f73a8a0c24beb93d88bdc3b67f4a7954/lab5/src/application/user_service.cpp) · [Проверка заголовка](https://github.com/Pavloffff/MAI_System_Design/blob/761a40c1f73a8a0c24beb93d88bdc3b67f4a7954/lab5/src/infrastructure/jwt/jwt_checker.cpp)

## Создание доклада

1. Узнайте `event_id` существующего мероприятия. Подготовьте название длиной от 3 до 200 символов и время окончания позже времени начала.
2. Отправьте `POST /talks` с полями `title`, `start_time`, `end_time`, `user_id` и `event_id`. Описание в поле `description` необязательно. Поле `user_id` требуется схемой запроса. После разбора JSON обработчик записывает в него идентификатор вошедшего пользователя из контекста запроса.
3. Сохраните `id` доклада из ответа. Сервис проверяет наличие пользователя, записывает доклад в PostgreSQL и при подключённом кэше сбрасывает общий список и список выбранного мероприятия. [Схема запроса](https://github.com/Pavloffff/MAI_System_Design/blob/761a40c1f73a8a0c24beb93d88bdc3b67f4a7954/lab5/docs/definitions/talks.yaml) · [Обработчик](https://github.com/Pavloffff/MAI_System_Design/blob/761a40c1f73a8a0c24beb93d88bdc3b67f4a7954/lab5/src/interfaces/rest/talks/talks_handler.cpp) · [Сервис докладов](https://github.com/Pavloffff/MAI_System_Design/blob/761a40c1f73a8a0c24beb93d88bdc3b67f4a7954/lab5/src/application/talk_service.cpp)

## Проверка результата

Запросите `GET /events/{event_id}/talks` с тем же идентификатором мероприятия. Найдите в JSON-массиве запись с сохранённым `id` и сверьте название и автора. Для просмотра всех докладов используйте `GET /talks`. При включённом кэше сервис сначала пытается прочитать сохранённый список. При промахе он получает данные из репозитория и сохраняет результат в кэш. [Маршруты](https://github.com/Pavloffff/MAI_System_Design/blob/761a40c1f73a8a0c24beb93d88bdc3b67f4a7954/lab5/configs/static_config.yaml) · [Выборка по мероприятию](https://github.com/Pavloffff/MAI_System_Design/blob/761a40c1f73a8a0c24beb93d88bdc3b67f4a7954/lab5/src/application/event_service.cpp)

## Если создание вернуло ошибку

Проверьте формат обязательных полей, существование мероприятия, длину названия и интервал времени. Ограничение таблицы `talks` требует `end_time > start_time`. В этой ревизии `Talk::CheckTimeInterval` возвращает логическое значение, которое вызывающий код игнорирует. Ошибка записи может поэтому дойти до общего обработчика исключений и вернуться клиенту как HTTP 500 с сообщением `Internal server error`. По одному этому сообщению установить причину конкретного сбоя нельзя. [Ограничения таблицы](https://github.com/Pavloffff/MAI_System_Design/blob/761a40c1f73a8a0c24beb93d88bdc3b67f4a7954/lab5/schema.sql) · [Проверка времени](https://github.com/Pavloffff/MAI_System_Design/blob/761a40c1f73a8a0c24beb93d88bdc3b67f4a7954/lab5/src/domain/talk.cpp)
