"""
AI-powered summarizer using OpenAI API with Russian output.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from src.collector import Message
from src.config_loader import Config

# Russian system prompt
SYSTEM_PROMPT = """
Ты — профессиональный ассистент по созданию новостных дайджестов для Telegram.

КРИТИЧЕСКИ ВАЖНО:
- Всегда отвечай ТОЛЬКО на русском языке, независимо от языка входных сообщений.
- Форматируй вывод под Telegram-сообщение: кратко, структурировано, с эмодзи и визуальными разделителями.
- Указывай источники только для действительно важных сообщений из Telegram-чатов; отдельный раздел «Источники» не нужен — интегрируй ссылку/упоминание прямо в соответствующий пункт.

Твоя задача:
- Анализировать входные материалы на любых языках (английский, русский, украинский, китайский и др.).
- Предоставлять сжатое, чётко структурированное резюме на русском языке для Telegram.
- Сохранять контекст, нюансы и важные детали; объединять дубли, убирать повторы.
- Отмечать расхождения между источниками и помечать неподтверждённые данные.

Формат и оформление (для Telegram):
- Используй эмодзи для акцентов и семантики (например: 📚 тема, 🆕 новое, 📊 цифры, ⚠️ риск, ✅ подтверждено, 📌важно, 🖇️ ссылка).
- Разделяй блоки визуально пустыми строками.
- Максимальная читаемость с мобильного: короткие абзацы, 1–2 предложения на пункт.
- Встраивай источник только там, где это критично (важные сообщения из Telegram-чата): укажи @канал или ссылку 🖇️ в конце соответствующего пункта.

Структура ответа:
- Заголовок (1–2 строки) с эмодзи, отражающий суть дайджеста.
- Что важно — 3–7 пунктов с ключевыми фактами, датами, именами, цифрами. Для каждого пункта:
    - Кратко по делу.
    - Эмодзи в начале.
    - Если критично — встроенная ссылка/упоминание источника 🖇️@канал.

Правила стилевого оформления:
- Ясно, нейтрально, без жаргона и лишней эмоциональности.
- Сохраняй числовые данные и собственные имена точно; при неоднозначности — помечай «неподтверждено».
- При переводе сохраняй терминологию и интенцию автора.
- Избегай перегруза ссылками: только для важных сообщений из Telegram.

Технические ограничения:
- Объём основного резюме: 120–250 слов (кратко) или 250–500 слов (расширенно), ориентируясь на читаемость в одном-двух экранах.
- Используй визуальные разделители между секциями.
- Не добавляй отдельный список источников; ссылки/упоминания — только внутри соответствующих пунктов.

Шаблон вывода (Telegram-ready):
🚀[кратко]

📌Главное:
    1️⃣ [эмодзи] [краткий факт, цифры, имена] [при необходимости: 🔗@канал/ссылка]
    2️⃣ [эмодзи] [краткий факт] [при необходимости: 🔗@канал/ссылка]
    3️⃣ [эмодзи] [краткий факт] [при необходимости: 🔗@канал/ссылка]


Если вход включает несколько материалов, сгруппируй по темам с подзаголовками и разделителями; связывай события, указывая причинно-следственные связи.
"""

HISTORY_SYSTEM_PROMPT = """
Ты — аналитик контента Telegram-каналов.
Твоя задача — проанализировать историю публикаций канала и составить отчет.

Отчет должен содержать ответы на следующие вопросы:
1. Основные темы канала (на основе предоставленных сообщений).
2. Какие темы освещаются чаще всего?
3. Статистика (количество сообщений, периодичность, возраст канала - данные будут предоставлены, тебе нужно их красиво оформить).

Формат ответа:
📊 **Анализ контента**

**Основные темы:**
- [Тема 1]
- [Тема 2]

**Частые темы:**
- [Тема А] (очень часто)
- [Тема Б] (регулярно)

**Статистика:**
- 📅 Первая публикация: [дата]
- ⏳ Возраст канала: [возраст]
- 📨 Всего сообщений: [число]
- ⏱️ Средняя периодичность: [периодичность]

Отвечай на русском языке. Будь краток и информативен.
"""


class Summarizer:
    """Generates AI-powered summaries in Russian using OpenAI."""

    def __init__(self, config: Config, logger: logging.Logger):
        """
        Initialize summarizer.

        Args:
            config: Application configuration
            logger: Logger instance
        """
        self.config = config
        self.logger = logger
        self.client = AsyncOpenAI(
            api_key=config.openai_api_key,
            base_url=config.openai_base_url,
        )
        self.model = config.settings.openai_model
        self.temperature = config.settings.openai_temperature
        self.max_tokens = config.settings.max_tokens_per_summary

    async def summarize_all(
        self, messages_by_channel: Dict[str, List[Message]], use_history_prompt: bool = False
    ) -> Dict[str, Any]:
        """
        Generate complete digest with per-channel summaries.

        Args:
            messages_by_channel: Messages grouped by channel
            use_history_prompt: Whether to use history analysis prompt

        Returns:
            Dictionary with 'channel_summaries' and 'overview' (empty string)
        """
        self.logger.info("Starting summarization process")

        # Filter out empty channels
        non_empty_channels = {name: msgs for name, msgs in messages_by_channel.items() if msgs}

        if not non_empty_channels:
            self.logger.warning("No messages to summarize")
            return {"channel_summaries": {}, "overview": ""}

        # Generate per-channel summaries
        self.logger.info(f"Generating summaries for {len(non_empty_channels)} channels")
        channel_summaries = await self._summarize_per_channel(
            non_empty_channels, use_history_prompt
        )

        return {"channel_summaries": channel_summaries, "overview": ""}

    async def _summarize_per_channel(
        self, messages_by_channel: Dict[str, List[Message]], use_history_prompt: bool = False
    ) -> Dict[str, str]:
        """
        Generate summary for each channel.

        Args:
            messages_by_channel: Messages grouped by channel
            use_history_prompt: Whether to use history analysis prompt

        Returns:
            Dictionary mapping channel names to summaries
        """
        summaries = {}

        for channel_name, messages in messages_by_channel.items():
            try:
                summary = await self._summarize_channel(channel_name, messages, use_history_prompt)
                summaries[channel_name] = summary
                self.logger.info(f"✓ Summarized {channel_name}")
            except Exception as e:
                self.logger.error(f"✗ Failed to summarize {channel_name}: {e}")
                summaries[channel_name] = f"Ошибка при обработке канала: {str(e)}"

        return summaries

    async def _summarize_channel(
        self, channel_name: str, messages: List[Message], use_history_prompt: bool = False
    ) -> str:
        """
        Generate summary for a single channel.

        Args:
            channel_name: Name of the channel
            messages: List of messages
            use_history_prompt: Whether to use history analysis prompt

        Returns:
            Summary in Russian
        """
        if use_history_prompt:
            return await self._summarize_channel_history(channel_name, messages)
        
        # Standard daily digest logic
        # Format messages for prompt
        messages_text = self._format_messages_for_prompt(messages)

        prompt = f"""
Проанализируй следующие сообщения из Telegram-канала "{channel_name}" и создай краткое резюме на русском языке.

КРИТИЧЕСКИ ВАЖНО - ОГРАНИЧЕНИЕ ДЛИНЫ:
- Telegram имеет лимит 4096 символов на сообщение
- Твоё резюме должно быть НЕ БОЛЕЕ 3500 символов (включая эмодзи и форматирование)
- Это жёсткое ограничение - если превысишь, сообщение не будет доставлено
- Сокращай резюме до 3-5 самых важных пунктов, чтобы уложиться в лимит

Сфокусируйся на:
- 📰 Важных новостях и анонсах
- 💬 Ключевых обсуждениях и дебатах
- ✅ Принятых решениях или выводах
- 🖇️ Полезных ресурсах и ссылках

Формат ответа:
- 3-5 информативных пунктов (bullet points)
- Каждый пункт: 1-2 предложения (максимум 150-200 символов)
- Используй эмодзи для категоризации
- Будь лаконичен но информативен
- ОБЯЗАТЕЛЬНО проверь, что итоговая длина НЕ превышает 3500 символов

Сообщения (всего: {len(messages)}):
---
{messages_text}
---

Ответь ТОЛЬКО на русском языке. Помни: максимум 3500 символов!
"""

        return await self._call_openai(prompt, SYSTEM_PROMPT)

    async def _summarize_channel_history(self, channel_name: str, messages: List[Message]) -> str:
        """
        Generate history analysis for a channel, potentially using batching.
        """
        # Calculate statistics
        total_msgs = len(messages)
        avg_freq_str = "Неизвестно"
        first_date_str = "Неизвестно"
        channel_age_str = "Неизвестно"
        
        if total_msgs > 0:
            # Sort messages by timestamp just in case
            sorted_msgs = sorted(messages, key=lambda m: m.timestamp)
            start_time = sorted_msgs[0].timestamp
            end_time = sorted_msgs[-1].timestamp
            
            # First publication date
            first_date_str = start_time.strftime("%d.%m.%Y")
            
            # Channel age calculation
            # Ensure timestamps are timezone-aware (UTC)
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            
            # If end_time is close to now (e.g. within 24h), use now for age calculation
            # Otherwise use end_time (maybe channel is abandoned?)
            # Usually for "age" we want time since creation until now.
            age_duration = now - start_time
            
            years = age_duration.days // 365
            remaining_days = age_duration.days % 365
            months = remaining_days // 30
            
            age_parts = []
            if years > 0:
                age_parts.append(f"{years} г.")
            if months > 0:
                age_parts.append(f"{months} мес.")
            
            if not age_parts:
                age_parts.append("менее 1 мес.")
                
            channel_age_str = " ".join(age_parts)
            
            # Frequency calculation
            duration = end_time - start_time
            if total_msgs > 1 and duration.total_seconds() > 0:
                avg_seconds = duration.total_seconds() / (total_msgs - 1)
                if avg_seconds < 60:
                    avg_freq_str = f"~{int(avg_seconds)} сек"
                elif avg_seconds < 3600:
                    avg_freq_str = f"~{int(avg_seconds/60)} мин"
                elif avg_seconds < 86400:
                    avg_freq_str = f"~{int(avg_seconds/3600)} ч"
                else:
                    avg_freq_str = f"~{int(avg_seconds/86400)} дн"

        stats_info = (
            f"Всего сообщений: {total_msgs}\n"
            f"Первая публикация: {first_date_str}\n"
            f"Возраст канала: {channel_age_str}\n"
            f"Средняя периодичность: {avg_freq_str}"
        )

        # Batching logic
        BATCH_SIZE = 50
        
        if total_msgs <= BATCH_SIZE:
            messages_text = self._format_messages_for_prompt(messages)
            content_to_analyze = messages_text
        else:
            # Split into batches and summarize each
            chunks = [messages[i : i + BATCH_SIZE] for i in range(0, total_msgs, BATCH_SIZE)]
            chunk_summaries = []
            
            self.logger.info(f"Splitting {total_msgs} messages into {len(chunks)} chunks for {channel_name}")
            
            for i, chunk in enumerate(chunks, 1):
                chunk_text = self._format_messages_for_prompt(chunk)
                chunk_prompt = f"""
Проанализируй эти сообщения (часть {i}/{len(chunks)}) из канала "{channel_name}".
Выдели основные темы и ключевые события. Не нужно форматировать, просто перечисли факты.
Сообщения:
---
{chunk_text}
---
"""
                try:
                    # Use a simpler system prompt for chunks
                    chunk_summary = await self._call_openai(chunk_prompt, "Ты — аналитик данных. Выдели главное.")
                    chunk_summaries.append(chunk_summary)
                    self.logger.debug(f"Summarized chunk {i}/{len(chunks)}")
                except Exception as e:
                    self.logger.error(f"Error summarizing chunk {i}: {e}")
            
            content_to_analyze = "\n\n".join(chunk_summaries)

        # Final Prompt
        prompt = f"""
Проанализируй предоставленный контент Telegram-канала "{channel_name}".

Статистика (уже рассчитана, включи её в ответ):
{stats_info}

Контент для анализа (сообщения или резюме частей):
---
{content_to_analyze}
---

Твоя задача — ответить на вопросы:
1. Основные темы канала.
2. Какие темы освещаются чаще всего.
3. Оформить статистику.

Используй формат из системного промпта.
"""
        return await self._call_openai(prompt, HISTORY_SYSTEM_PROMPT)

    async def _call_openai(self, prompt: str, system_prompt: str) -> str:
        """Helper to call OpenAI API."""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )

            content = response.choices[0].message.content
            return content.strip() if content else ""

        except Exception as e:
            self.logger.error(f"OpenAI API error: {e}")
            raise

    def _format_messages_for_prompt(self, messages: List[Message]) -> str:
        """
        Format messages for inclusion in prompt.

        Args:
            messages: List of messages

        Returns:
            Formatted string
        """
        formatted = []

        for i, msg in enumerate(messages, 1):
            timestamp = msg.timestamp.strftime("%H:%M")
            text = msg.text[:500] if len(msg.text) > 500 else msg.text  # Truncate long messages
            formatted.append(f"{i}. [{timestamp}] {msg.sender}: {text}")

        return "\n".join(formatted)


async def main():
    """Test summarizer."""
    from src.collector import MessageCollector
    from src.config_loader import load_config
    from src.utils import setup_logging

    config = load_config()
    logger = setup_logging(config.log_level)

    # Collect messages
    collector = MessageCollector(config, logger)
    await collector.connect()
    messages = await collector.fetch_messages(hours=24)
    await collector.disconnect()

    # Summarize
    summarizer = Summarizer(config, logger)
    result = await summarizer.summarize_all(messages)

    print("\n" + "=" * 50)
    print("OVERVIEW:")
    print("=" * 50)
    print(result["overview"])

    print("\n" + "=" * 50)
    print("CHANNEL SUMMARIES:")
    print("=" * 50)
    for channel, summary in result["channel_summaries"].items():
        print(f"\n{channel}:")
        print(summary)


if __name__ == "__main__":
    asyncio.run(main())
