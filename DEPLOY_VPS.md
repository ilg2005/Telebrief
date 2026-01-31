# Руководство по развертыванию Telebrief на VPS

Этот документ описывает пошаговый процесс запуска бота Telebrief на VPS сервере с использованием Docker.

## Предварительные требования

1. **VPS сервер** (Ubuntu 22.04/24.04 или Debian 11/12).
2. **Установленный Docker и Docker Compose**.
   Если Docker еще не установлен, выполните следующие команды:

   ```bash
   # Обновление пакетов
   sudo apt update && sudo apt upgrade -y

   # Установка Docker
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh

   # Добавление текущего пользователя в группу docker (чтобы не писать sudo каждый раз)
   sudo usermod -aG docker $USER
   newgrp docker
   ```

## Шаг 1: Загрузка проекта

Выберите один из способов загрузки кода на ваш VPS. Мы будем клонировать ветку `openrouter_integration`, как наиболее актуальную.

### Вариант 1: Через HTTPS (Git)
Самый простой способ, не требующий настройки ключей (для публичных репозиториев).

```bash
# Клонируем конкретную ветку openrouter_integration
git clone -b openrouter_integration https://github.com/ilg2005/Telebrief.git

# Переходим в папку проекта
cd Telebrief
```

### Вариант 2: Через SSH
Используйте этот метод, если вы добавили свой SSH-ключ в GitHub. Это удобнее для обновлений и работы с приватными репозиториями.

```bash
git clone -b openrouter_integration git@github.com:ilg2005/Telebrief.git
cd Telebrief
```

### Вариант 3: Через GitHub CLI (gh)
Если у вас установлена утилита `gh` и вы авторизованы (`gh auth login`):

```bash
gh repo clone ilg2005/Telebrief -- -b openrouter_integration
cd Telebrief
```

> **Примечание:** Если у вас приватный репозиторий, вам потребуется настроить SSH ключи или использовать HTTPS с токеном.

## Шаг 2: Настройка конфигурации

Проект требует создания двух конфигурационных файлов.

### 2.1. Настройка переменных окружения (.env)

Скопируйте пример файла конфигурации:

```bash
cp .env.example .env
```

Откройте файл `.env` для редактирования (например, через `nano`):

```bash
nano .env
```

Заполните следующие обязательные поля:
- `TELEGRAM_API_ID` и `TELEGRAM_API_HASH`: Получить на [my.telegram.org](https://my.telegram.org).
- `TELEGRAM_BOT_TOKEN`: Токен вашего бота от [@BotFather](https://t.me/BotFather).
- `OPENAI_API_KEY`: Ваш ключ API (OpenAI или OpenRouter).
- `OPENAI_BASE_URL`: Если используете OpenRouter или другой прокси (иначе оставьте по умолчанию).

### 2.2. Создание Telegram сессии (ОБЯЗАТЕЛЬНО)

Перед запуском необходимо авторизоваться в Telegram, чтобы создать файл сессии.

```bash
# Запустите скрипт создания сессии
chmod +x create_session.sh
./create_session.sh
```

Следуйте инструкциям на экране: введите номер телефона и код подтверждения.
Это создаст файл `sessions/user.session`, который будет использоваться ботом.

### 2.3. Настройка параметров бота (config.yaml)

Скопируйте пример конфига:

```bash
cp config.yaml.example config.yaml
```

Откройте файл `config.yaml`:

```bash
nano config.yaml
```

**Важно настроить:**
1. **channels**: Добавьте список каналов для мониторинга.
   - Для публичных каналов используйте `@username`.
   - Для приватных — ID (начинается с `-100`, можно узнать через пересылку поста боту @RawDataBot).
2. **target_user_id**: Укажите ваш Telegram ID (узнать у @userinfobot), чтобы бот отправлял дайджесты именно вам.
3. **schedule_time**: Время отправки дайджеста (в UTC).

## Шаг 3: Запуск через Docker

Запустите контейнер в фоновом режиме:

```bash
docker compose up -d --build
```

> Если у вас старая версия Docker, используйте команду `docker-compose up -d --build`.

### Проверка статуса

Убедитесь, что контейнер запущен:

```bash
docker compose ps
```

Посмотрите логи, чтобы убедиться в отсутствии ошибок:

```bash
docker compose logs -f
```

(Нажмите `Ctrl+C`, чтобы выйти из просмотра логов).

## Управление и Обслуживание

### Перезапуск бота
Если вы изменили `config.yaml` или `.env`, перезапустите контейнер:

```bash
docker compose restart
```

### Обновление версии
Чтобы обновить код бота до последней версии из репозитория:

```bash
# 1. Получить свежий код
git pull

# 2. Пересобрать и перезапустить контейнер
docker compose up -d --build
```

### Остановка
Чтобы полностью остановить бота:

```bash
docker compose down
```

## Где хранятся данные?

В файле `docker-compose.yml` настроены volume-маунты, поэтому данные сохраняются на хосте даже после пересоздания контейнеров:

- `./sessions`: Сессии Telegram (чтобы не входить заново).
- `./data`: База данных `telebrief.db` и настройки времени выполнения.
- `./logs`: Логи работы приложения.
