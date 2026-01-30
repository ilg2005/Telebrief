# Telebrief — Developer Guide (RU)

Этот документ описывает устройство Telebrief для разработчиков: основные возможности, поток выполнения, конфигурацию и карту файлов.

## Что это такое

Telebrief — сервис, который:

- читает сообщения из списка Telegram-каналов/чатов (включая приватные) через **Telethon** (User API);
- генерирует краткие summaries **на русском** через **OpenAI-compatible API**;
- отправляет дайджест в Telegram через **python-telegram-bot** (Bot API);
- поддерживает ежедневный автозапуск по расписанию (APScheduler) и запуск по команде;
- рассчитан на **одного** авторизованного пользователя (`target_user_id`).

Важно: бот работает через **long polling**, HTTP-сервера нет.

## Высокоуровневая архитектура

Компоненты:

- **Entry point / wiring**: `main.py`
- **Bot API (команды, UX, long polling)**: `src/bot_commands.py`
- **Scheduler (cron, ежедневный запуск)**: `src/scheduler.py`
- **Pipeline генерации**: `src/core.py`
  - сбор: `src/collector.py` (Telethon)
  - суммаризация: `src/summarizer.py` (LLM)
  - форматирование: `src/formatter.py` (Markdown под Telegram)
  - отправка: `src/sender.py`
- **Хранилище (SQLite)**: `src/chat_storage.py`
- **Q/A по истории + источники**: `src/chat_answerer.py`

Поток данных для “обычного” дайджеста:

1) Scheduler или команда бота инициирует генерацию.
2) Collector собирает сообщения по каналам за период.
3) Summarizer генерирует summary для каждого канала.
4) Formatter строит текст сообщений.
5) Sender отправляет сообщения пользователю и (опционально) чистит старые дайджесты.

## Конфигурация и состояние

### `.env` (секреты и пути)

Пример: `.env.example`.

Основное:

- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` — учётка Telegram App (Telethon).
- `TELEGRAM_BOT_TOKEN` — токен Bot API.
- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` — OpenAI-compatible провайдер (по умолчанию ориентир на OpenRouter).
- `TELEBRIEF_CHAT_DB_PATH` — путь к SQLite (`data/telebrief.db` по умолчанию).
- `TELEBRIEF_RUNTIME_SETTINGS_PATH` — runtime overrides (`data/runtime_settings.json`).
- `LOG_LEVEL` — уровень логов.

### `config.yaml` (настройки + seed каналов)

Пример: `config.yaml.example`.

Содержит:

- `channels`: список каналов/чатов (используется как seed на старте).
- `settings`: расписание, timezone, лимиты, `target_user_id` и т.д.

### SQLite `data/telebrief.db` (источник правды)

`data/telebrief.db` — основное хранилище, в частности:

- таблица `channels`: список каналов/чатов, их имя и порядок.
- таблицы `chat_sessions`, `chat_corpus_messages`, `chat_turns`: состояние “чата по истории”.

На старте приложение:

- берёт `channels` из `config.yaml` как seed,
- upsert’ит их в SQLite,
- дальше работает со списком каналов из SQLite.

### Runtime overrides: `data/runtime_settings.json`

Файл хранит настройки, которые можно менять “на лету” из бота, без рестарта:

- `enable_scheduler` — включение/выключение scheduler
- `openai_model` — override модели генерации

Приоритет модели:

1) `openai_model` из `data/runtime_settings.json` (если есть),
2) `OPENAI_MODEL` из env,
3) `settings.openai_model` из `config.yaml`.

### Персистентные директории

- `sessions/` — Telethon user session (`sessions/user.session`). Это обязательная часть состояния.
- `data/` — SQLite + runtime settings + служебные JSON (например, для cleanup).

Для миграций/бэкапов минимум: `sessions/` + `data/`.

## Точки входа

- `main.py` — основной entry point.
- `create_session.py` / `create_session.sh` — одноразовое создание Telethon сессии (`sessions/user.session`).

## Команды бота (кратко)

Актуальный список — в `README.md`.

Ключевое:

- `/digest` — дайджест за последние N часов (дефолт 24).
- `/history` — анализ истории канала (период/канал).
- `/chat` — вопросы по выбранной истории/контексту.
- `/model` — показать/поменять модель (persist).
- `/autoschedule on|off` — включить/выключить автодайджест (persist).
- `/cleanup` — вручную удалить старые дайджесты.

## Карта репозитория

### Корень

- `main.py` — инициализация и lifecycle приложения.
- `README.md` — пользовательская документация (деплой, команды).
- `Dockerfile`, `docker-compose.yml` — контейнеризация и тома.
- `requirements.txt`, `requirements-dev.txt`, `pyproject.toml` — зависимости и настройки инструментов.
- `Makefile` — команды `make test`, `make lint`, `make format`.
- `config.yaml.example`, `.env.example` — примеры конфигов.
- `create_session.py`, `create_session.sh` — генерация Telethon session.

### `src/`

- `config_loader.py` — сборка итогового конфига (env + yaml + SQLite + runtime overrides).
- `scheduler.py` — APScheduler cron job.
- `bot_commands.py` — Telegram Bot API: команды, inline-меню, авторизация.
- `core.py` — основной pipeline генерации/отправки (обычный режим и history).
- `collector.py` — Telethon, сбор сообщений по каналам/периоду.
- `summarizer.py` — OpenAI client, промпты (RU-only), генерация summaries.
- `formatter.py` — Markdown-форматирование сообщений/дайджеста.
- `sender.py` — отправка сообщений и cleanup.
- `chat_storage.py` — SQLite schema и операции (channels + chat sessions/corpus).
- `chat_answerer.py` — ответы по корпусу с цитированием источников.
- `runtime_settings.py` — чтение/запись `data/runtime_settings.json`.
- `utils.py` — логирование и утилиты (в т.ч. трекинг message_ids для cleanup).

### `tests/`

Unit-тесты ключевых модулей и пайплайна.

## Разработка и тестирование

Быстрые ориентиры:

- Установка dev-зависимостей: `pip install -r requirements-dev.txt`
- Тесты: `make test-fast` (быстро) или `make test` (с coverage)
- Линт/типы: `make lint`
- Автоформатирование: `make format`

## Где менять поведение

- Формат и структура дайджеста: `src/formatter.py`
- Промпты/тональность/язык summaries: `src/summarizer.py`
- Команды/UX и флоу взаимодействия: `src/bot_commands.py`
- Планирование: `src/scheduler.py`
- Правила хранения истории/чата: `src/chat_storage.py`, `src/chat_answerer.py`

## Частые проблемы (диагностика)

- Нет сообщений/каналов: проверьте `data/telebrief.db` (таблица `channels`) и/или seed в `config.yaml`.
- Не отправляет сообщения: проверьте `target_user_id` и авторизацию (бот отвечает только этому пользователю).
- Проблемы доступа к приватным каналам: проверьте, что `sessions/user.session` создан и аккаунт имеет доступ.
- Ошибки LLM: проверьте `OPENAI_API_KEY`, `OPENAI_BASE_URL` и модель (включая override через `/model`).
