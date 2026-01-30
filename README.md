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

1. **Python 3.10+** - [Download Python](https://www.python.org/downloads/)

2. **Telegram App Credentials** - [Get from my.telegram.org](https://my.telegram.org)
   - `api_id` and `api_hash`

3. **Telegram Bot Token** - Create via [@BotFather](https://t.me/BotFather)
   - Send `/newbot` to create a new bot
   - Save the bot token

4. **OpenAI API Key** - [Get from platform.openai.com](https://platform.openai.com)
   - Requires GPT-5-nano access

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

## 🤖 Bot Commands

Open Telegram and message your bot:

| Command | Description |
|---------|-------------|
| `/start` | Show welcome message and available commands |
| `/help` | Display help message with all commands |
| `/digest` | Generate and send digest for last 24 hours instantly |
| `/history` | Analyze channel history (period + channel menu) |
| `/status` | Show configuration, next scheduled run, and system info |
| `/model` | Show or set the OpenRouter model for generation |
| `/autoschedule on|off` | Enable/disable daily auto-digests |
| `/cleanup` | Manually delete old digest messages |

**Model selection**:
- Run `/model` to see the current model and the default one
- Run `/model <id>` to set a model ID copied from OpenRouter (e.g. `anthropic/claude-3.5-sonnet`)
- Use the “Reset to default” button to revert back to the default model from config/env

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
