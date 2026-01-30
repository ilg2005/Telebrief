import logging
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from src.config_loader import Config


SYSTEM_PROMPT = """
Ты — ассистент, который отвечает на вопросы по истории Telegram-канала.

Правила:
- Отвечай ТОЛЬКО по предоставленному контексту (сообщения из канала).
- Если в контексте нет ответа, так и скажи и уточни, что нужно искать.
- Будь кратким и конкретным.
- Если ты используешь информацию из сообщения, ставь ссылку-цитату в виде [N] прямо после предложения.
- Используй ТОЛЬКО номера [N], которые есть в контексте.
- В конце добавь раздел 'Источники:' и перечисли только те [N], которые реально использовал, вместе со ссылкой из контекста.
"""


class ChatAnswerer:
    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.client = AsyncOpenAI(
            api_key=config.openai_api_key,
            base_url=config.openai_base_url,
        )
        self.model = config.settings.openai_model
        self.temperature = max(0.0, min(float(config.settings.openai_temperature), 1.0))

    async def answer(
        self,
        question: str,
        context_snippets: str,
        chat_turns: List[Dict[str, str]],
        channel_name: Optional[str] = None,
    ) -> str:
        channel_part = f"Канал: {channel_name}\n" if channel_name else ""
        user_prompt = (
            f"{channel_part}"
            f"Вопрос: {question}\n\n"
            "Контекст (сообщения из канала):\n"
            "-----\n"
            f"{context_snippets}\n"
            "-----\n\n"
            "Ответь на русском языке. Следуй правилам цитирования из системного промпта."
        )

        messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for t in chat_turns:
            role = t.get("role")
            content = t.get("content")
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_prompt})

        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
            )
            content = resp.choices[0].message.content
            return content.strip() if content else ""
        except Exception as e:
            self.logger.error(f"ChatAnswerer OpenAI API error: {e}")
            raise
