import asyncio
import logging
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Set, Tuple

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

SELECTOR_SYSTEM_PROMPT = """
Ты — ассистент, который помогает выбрать релевантные сообщения из истории Telegram-канала.

Правила:
- Тебе дадут вопрос и фрагмент контекста с сообщениями, каждое имеет номер [N].
- Верни ТОЛЬКО номера релевантных сообщений в формате: [12], [45], [78]
- Никакого текста, пояснений, списков, заголовков.
- Если релевантных сообщений нет — верни пустую строку.
"""

SINGLE_PASS_CONTEXT_CHAR_LIMIT = 45_000
MAP_CHUNK_CONTEXT_CHAR_LIMIT = 12_000
MAP_CHUNK_MAX_MESSAGES = 80
MAP_CONCURRENCY_LIMIT = 3
MAX_SELECTED_MESSAGES = 200


class LLMResponseError(RuntimeError):
    pass


class ChatAnswerer:
    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.client = AsyncOpenAI(
            api_key=config.openai_api_key,
            base_url=config.openai_base_url,
        )

    def _current_model(self) -> str:
        return str(self.config.settings.openai_model).strip()

    def _current_temperature(self) -> float:
        return max(0.0, min(float(self.config.settings.openai_temperature), 1.0))

    @staticmethod
    def _extract_content(resp: Any) -> str:
        try:
            choices = getattr(resp, "choices", None)
            if not choices or not isinstance(choices, list):
                return ""
            first = choices[0]
            message = getattr(first, "message", None)
            if message is None:
                return ""
            content = getattr(message, "content", None)
            return content.strip() if isinstance(content, str) and content.strip() else ""
        except Exception:
            return ""

    @staticmethod
    def _format_corpus_message(index: int, message: Dict[str, Any]) -> Tuple[str, str]:
        text = (message.get("text") or "").replace("\n", " ").strip()
        if len(text) > 900:
            text = text[:900] + "…"
        link = message.get("link") or "#"
        snippet = f"[{index}] [{message.get('timestamp')}] {message.get('sender')}: {text}\nСсылка: {link}"
        return snippet, link

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        resp = await self.client.chat.completions.create(
            model=self._current_model(),
            messages=messages,
            temperature=temperature,
        )
        content = self._extract_content(resp)
        if content:
            return content
        raise LLMResponseError("Провайдер LLM вернул пустой ответ.")

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
                model=self._current_model(),
                messages=messages,
                temperature=self._current_temperature(),
            )
            content = self._extract_content(resp)
            if content:
                return content
            raise LLMResponseError("Провайдер LLM вернул пустой ответ.")
        except Exception as e:
            self.logger.error(f"ChatAnswerer OpenAI API error: {e}")
            raise

    async def answer_full_scan(
        self,
        question: str,
        messages: Sequence[Dict[str, Any]],
        chat_turns: List[Dict[str, str]],
        channel_name: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> Tuple[str, Dict[int, str], List[str]]:
        total_messages = len(messages)
        if total_messages == 0:
            return "", {}, []

        snippets: List[str] = []
        all_links: List[str] = []
        all_index_to_link: Dict[int, str] = {}
        used_chars = 0

        for i, m in enumerate(messages, 1):
            snippet, link = self._format_corpus_message(i, m)
            snippets.append(snippet)
            used_chars += len(snippet)
            if link != "#":
                all_links.append(link)
                all_index_to_link[i] = link

        if used_chars <= SINGLE_PASS_CONTEXT_CHAR_LIMIT:
            context_snippets = "\n\n".join(snippets)
            answer = await self.answer(
                question=question,
                context_snippets=context_snippets,
                chat_turns=chat_turns,
                channel_name=channel_name,
            )
            return answer, all_index_to_link, all_links

        chunk_specs: List[Tuple[int, int, str]] = []
        chunk_parts: List[str] = []
        chunk_start = 1
        chunk_chars = 0
        for i, snippet in enumerate(snippets, 1):
            if chunk_parts and (
                chunk_chars + len(snippet) > MAP_CHUNK_CONTEXT_CHAR_LIMIT
                or len(chunk_parts) >= MAP_CHUNK_MAX_MESSAGES
            ):
                chunk_specs.append((chunk_start, i - 1, "\n\n".join(chunk_parts)))
                chunk_parts = []
                chunk_start = i
                chunk_chars = 0
            chunk_parts.append(snippet)
            chunk_chars += len(snippet)
        if chunk_parts:
            chunk_specs.append((chunk_start, total_messages, "\n\n".join(chunk_parts)))

        sem = asyncio.Semaphore(MAP_CONCURRENCY_LIMIT)
        progress_done = 0
        progress_lock = asyncio.Lock()
        map_failures = 0
        map_failures_lock = asyncio.Lock()

        async def select_for_chunk(
            _chunk_index: int, total_chunks: int, chunk_text: str
        ) -> Set[int]:
            async with sem:
                user_prompt = (
                    f"Вопрос: {question}\n\n"
                    "Контекст (сообщения из канала):\n"
                    "-----\n"
                    f"{chunk_text}\n"
                    "-----"
                )

                raw = ""
                last_error: Optional[Exception] = None
                for attempt in range(3):
                    try:
                        raw = await self._call_llm(
                            system_prompt=SELECTOR_SYSTEM_PROMPT,
                            user_prompt=user_prompt,
                            temperature=0.0,
                        )
                        break
                    except Exception as e:
                        last_error = e
                        await asyncio.sleep(0.5 * (2**attempt))

                if last_error and not raw:
                    nonlocal map_failures
                    async with map_failures_lock:
                        map_failures += 1
                    self.logger.warning(f"Map chunk failed: {last_error}")

                indices = {int(x) for x in re.findall(r"\[(\d{1,6})\]", raw)}
                if progress_callback:
                    nonlocal progress_done
                    async with progress_lock:
                        progress_done += 1
                        done = progress_done
                    await progress_callback(done, total_chunks)
                return indices

        total_chunks = len(chunk_specs)
        tasks = [
            asyncio.create_task(select_for_chunk(idx, total_chunks, spec[2]))
            for idx, spec in enumerate(chunk_specs, 1)
        ]
        selected_sets = await asyncio.gather(*tasks, return_exceptions=True)
        selected: Set[int] = set()
        for s in selected_sets:
            if isinstance(s, Exception):
                async with map_failures_lock:
                    map_failures += 1
                self.logger.warning(f"Map chunk task failed: {s}")
                continue
            selected.update(s)

        selected = {i for i in selected if 1 <= i <= total_messages}
        if not selected:
            if map_failures >= max(1, total_chunks // 2):
                return (
                    "Провайдер ответов временно вернул пустые ответы во время анализа. Попробуй повторить запрос через 10–20 секунд.",
                    {},
                    [],
                )
            return (
                "В выбранном периоде не нашёл сообщений, которые отвечают на вопрос. Попробуй уточнить формулировку.",
                {},
                [],
            )

        selected_indices = sorted(selected)[:MAX_SELECTED_MESSAGES]
        selected_snippets: List[str] = []
        selected_links: List[str] = []
        selected_index_to_link: Dict[int, str] = {}
        selected_chars = 0
        for i in selected_indices:
            snippet = snippets[i - 1]
            if selected_snippets and selected_chars + len(snippet) > SINGLE_PASS_CONTEXT_CHAR_LIMIT:
                break
            selected_snippets.append(snippet)
            selected_chars += len(snippet)
            link = all_index_to_link.get(i)
            if link:
                selected_index_to_link[i] = link
                selected_links.append(link)

        context_snippets = "\n\n".join(selected_snippets)
        answer = await self.answer(
            question=question,
            context_snippets=context_snippets,
            chat_turns=chat_turns,
            channel_name=channel_name,
        )
        return answer, selected_index_to_link, selected_links
