<div align="center">
  <img src="misc/logo.png" alt="Telebrief Logo" width="200"/>

  # Telebrief

  **Automated Telegram Digest Generator powered by GPT-5-nano**

  Telebrief collects messages from your Telegram channels (in any language), generates AI-powered summaries, and delivers beautiful daily digests **in Russian** directly to your Telegram account.
</div>

---

## ✨ Features

- 🌐 **Multi-language Support** - Reads channels in ANY language (English, Russian, Ukrainian, Chinese, etc.)
- 🇷🇺 **Russian Output Only** - All summaries generated in Russian regardless of source language
- 🤖 **GPT-5-nano Powered** - High-quality AI summarization with ultra-low cost (~$0.30/month)
- ⏰ **Scheduled & On-Demand** - Daily automatic digests + instant generation via bot commands
- 🔒 **Private Channel Support** - Access your private chats and channels
- 🎨 **Smart Formatting** - Markdown with emojis, bullet points, and clickable message links
- 🔐 **Secure** - Single-user only, credentials stored safely
- 🧹 **Auto-cleanup** - Automatically removes old digest messages

---

## 📋 Prerequisites

Before you begin, you'll need:

1. **Python 3.12+** - [Download Python](https://www.python.org/downloads/)

2. **Telegram App Credentials** - [Get from my.telegram.org](https://my.telegram.org)
   - `api_id` and `api_hash`

3. **Telegram Bot Token** - Create via [@BotFather](https://t.me/BotFather)
   - Send `/newbot` to create a new bot
   - Save the bot token

4. **OpenAI-compatible API Key**
   - Works with OpenRouter (recommended) or any OpenAI-compatible provider

5. **Your Telegram User ID** - Get from [@userinfobot](https://t.me/userinfobot)
   - Send `/start` to get your ID

---

## 🐳 Docker Deployment

Telebrief can be run in Docker for easy deployment. **No Python installation required on host!**

```bash
# 1. Create Telegram session (REQUIRED - one-time setup)
./create_session.sh

# 2. Start the service
docker compose up -d

# 3. View logs
docker compose logs -f telebrief
```

**Important**: You must create the Telegram session file BEFORE running Docker. The script uses Docker itself, so no additional dependencies needed.

**Tip**: If you want to generate digests only on demand, disable auto mode in the bot: `/autoschedule off`.

---

## 🖥️ VPS Docker Deploy (Long Polling)

Telebrief works via **long polling** (it does not expose an HTTP server), so you **do not need** Nginx/reverse-proxy for it.

### First-time setup

1) **Prepare files on the server**

```bash
git clone <your-repo-url>
cd Telebrief

cp .env.example .env
cp config.yaml.example config.yaml
```

2) **Fill `.env` and `config.yaml`**

- `.env`: Telegram API credentials + bot token + OpenRouter/OpenAI key
- `config.yaml`: `target_user_id` and initial channel list (optional; you can add/remove channels via the bot later)

3) **Create Telegram session (required once)**

```bash
./create_session.sh
```

This generates `sessions/user.session`. You can run it on the VPS (via SSH) or generate it locally and copy the `sessions/` directory to the server.

4) **Start**

```bash
docker compose up -d
docker compose logs -f telebrief
```

### Migration (move to VPS without losing `sessions/` and `data/`)

If you already have a working instance elsewhere (local machine / another server), copy the persistent directories to the new VPS.

1) Stop the service on the destination VPS:

```bash
docker compose down
```

2) Copy persistent data from the source machine to the VPS.

**Option A: rsync (recommended)**

```bash
rsync -avz ./sessions/ ./data/ user@vps:/opt/telebrief/
rsync -avz ./.env ./config.yaml ./docker-compose.yml user@vps:/opt/telebrief/
```

**Option B: scp**

```bash
scp -r ./sessions ./data user@vps:/opt/telebrief/
scp ./.env ./config.yaml ./docker-compose.yml user@vps:/opt/telebrief/
```

3) Start on the VPS:

```bash
cd /opt/telebrief
docker compose up -d
docker compose logs -f telebrief
```

Tip: if you're migrating from a running server, stop the old container first to avoid concurrent writes to SQLite.

### Persistence & backups

- `sessions/` must be preserved (Telegram user session)
- `data/` must be preserved (SQLite DB + runtime settings)
- Minimum backup: `sessions/` + `data/`

### Updating

```bash
git pull
docker compose build --pull
docker compose up -d
docker compose logs -f telebrief
```

### Notes

- The channel list is persisted in SQLite (`data/telebrief.db`), so `config.yaml` can be mounted read-only in Docker.
- `/version` shows `TELEBRIEF_BUILD_ID` (set it in `.env` if you want to see the deployed revision).
- `/chat` answers are based on the full chat context for the selected period, so large periods may take longer to answer.
- “All time” is still bounded by `max_messages_per_channel` (safety limit) when collecting messages from Telegram.

---

## 🤖 Bot Commands

Open Telegram and message your bot:

| Command | Description |
|---------|-------------|
| `/start` | Show welcome message and available commands |
| `/help` | Display help message with all commands |
| `/digest` | Generate and send digest for last 24 hours instantly |
| `/history` | Analyze channel history (period + channel menu) |
| `/status` | Show configuration, next scheduled run, and system info |
| `/version` | Show running build/version (useful after updates) |
| `/model` | Show or set the OpenRouter model for generation |
| `/chat` | Ask questions about the selected channel history |
| `/chat_status` | Show current chat context |
| `/chat_reset` | Rebuild chat context from the channel |
| `/chat_stop` | Exit chat mode |
| `/autoschedule on|off` | Enable/disable daily auto-digests |
| `/cleanup` | Manually delete old digest messages |

**Model selection**:
- Run `/model` to see the current model and the default one
- Run `/model <id>` to set a model ID copied from OpenRouter (e.g. `anthropic/claude-3.5-sonnet`)
- Use the “Reset to default” button to revert back to the default model from config/env
- Note: `/model` applies immediately (no bot restart needed).
- Note: model override is persisted in `data/runtime_settings.json` and has higher priority than `OPENAI_MODEL`. Use “Reset to default” (or delete `openai_model` from the file) to return to env/default.

**Chat citations (sources)**:
- Chat answers include citations like `[2]` that refer to a specific message in the context.
- The `Источники:` block lists only the cited message links as `- [2] https://t.me/.../495` so you can click and jump to the exact post.
- If you don't see `[N]` in the answer, you are likely running an older build. Check `/version` (or `/status`) after updating.

---

## 📊 Example Output

```markdown
# 📊 Ежедневный дайджест - 14 декабря 2025

## 🎯 Краткий обзор

Сегодня основные темы: запуск Python 3.13 с улучшениями производительности
обсуждался в нескольких технических каналах, криптовалютный рынок показал
высокую волатильность на фоне новостей о регулировании.

---

## 💻 TechCrunch

- 🚀 **Python 3.13 релиз**: Официально выпущена новая версия с JIT-компиляцией
- 🤖 **OpenAI анонсировала GPT-5**: Следующее поколение модели ожидается в Q1 2026
- 📱 **Apple vs EU**: Новые требования по interoperability

## 💰 Crypto News

- 📈 **Bitcoin волатильность**: Цена колебалась между $43K и $46K
- ⚠️ **SEC предупреждение**: Новая схема мошенничества
- 🔐 **Ethereum upgrade**: Успешно завершен тестнет

---
📈 **Статистика**: 20 каналов, 1,847 сообщений обработано
```

---

## 🛠️ Development & Testing

### Running Tests

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run all tests with coverage
make test

# Run linters
make lint

# Auto-format code
make format
```

---

## ❓ FAQ

**Q: Can I use this for non-Russian output?**
A: Yes! Edit the prompts in `src/summarizer.py` to change output language.

**Q: How many channels can I monitor?**
A: Tested up to 50 channels. Performance depends on message volume.

**Q: Can multiple users receive digests?**
A: Currently single-user only. Multi-user support would require database and additional auth logic.

**Q: Does it work with group chats?**
A: Yes! Add group chat IDs to `config.yaml` the same way as channels.

**Q: Can I customize the digest format?**
A: Yes! Edit `src/formatter.py` to change Markdown structure, emojis, and sections.

**Q: How much does it cost to run?**
A: Approximately **$0.30/month** with GPT-5-nano (ultra-affordable pricing). Based on ~20 channels with medium activity.

---


## 🙏 Credits

**Built with:**
- [Telethon](https://github.com/LonamiWebs/Telethon) - Telegram User API
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Bot API
- [OpenAI API](https://openai.com) - GPT-5-nano Summarization
- [APScheduler](https://github.com/agronholm/apscheduler) - Task Scheduling

---

<div align="center">
  <strong>Happy digesting! 📊🤖</strong>
</div>
