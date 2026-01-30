from unittest.mock import AsyncMock

import pytest

import src.chat_answerer as chat_answerer
from src.chat_answerer import ChatAnswerer


@pytest.mark.unit
@pytest.mark.asyncio
async def test_answer_full_scan_single_pass_includes_all_messages(sample_config, mock_logger):
    answerer = ChatAnswerer(sample_config, mock_logger)
    answerer.answer = AsyncMock(return_value="Ок. [1]")

    messages = [
        {
            "message_id": 10,
            "timestamp": "2026-01-01T00:00:00",
            "sender": "Alice",
            "text": "Первое сообщение",
            "link": "https://t.me/test/10",
        },
        {
            "message_id": 11,
            "timestamp": "2026-01-01T00:01:00",
            "sender": "Bob",
            "text": "Второе сообщение",
            "link": "https://t.me/test/11",
        },
    ]

    answer, index_to_link, links = await answerer.answer_full_scan(
        question="Вопрос",
        messages=messages,
        chat_turns=[],
        channel_name="Test Channel",
    )

    assert answer == "Ок. [1]"
    called_context = answerer.answer.call_args.kwargs["context_snippets"]
    assert "[1]" in called_context
    assert "[2]" in called_context
    assert index_to_link == {1: "https://t.me/test/10", 2: "https://t.me/test/11"}
    assert links == ["https://t.me/test/10", "https://t.me/test/11"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_answer_full_scan_map_reduce_selects_relevant_messages(
    monkeypatch, sample_config, mock_logger
):
    monkeypatch.setattr(chat_answerer, "SINGLE_PASS_CONTEXT_CHAR_LIMIT", 500)
    monkeypatch.setattr(chat_answerer, "MAP_CHUNK_CONTEXT_CHAR_LIMIT", 100_000)
    monkeypatch.setattr(chat_answerer, "MAP_CHUNK_MAX_MESSAGES", 2)
    monkeypatch.setattr(chat_answerer, "MAP_CONCURRENCY_LIMIT", 1)
    monkeypatch.setattr(chat_answerer, "MAX_SELECTED_MESSAGES", 50)

    answerer = ChatAnswerer(sample_config, mock_logger)
    answerer._call_llm = AsyncMock(side_effect=["[2]", "", "[5]"])
    answerer.answer = AsyncMock(return_value="Финал. [2] [5]")
    progress = AsyncMock()

    messages = []
    for i in range(1, 7):
        messages.append(
            {
                "message_id": i,
                "timestamp": f"2026-01-01T00:0{i}:00",
                "sender": f"User{i}",
                "text": "x" * 120,
                "link": f"https://t.me/test/{i}",
            }
        )

    answer, index_to_link, links = await answerer.answer_full_scan(
        question="Про что тут?",
        messages=messages,
        chat_turns=[],
        channel_name="Test Channel",
        progress_callback=progress,
    )

    assert answer == "Финал. [2] [5]"

    called_context = answerer.answer.call_args.kwargs["context_snippets"]
    assert "[2]" in called_context
    assert "[5]" in called_context
    assert "[1]" not in called_context
    assert "[6]" not in called_context

    assert index_to_link == {2: "https://t.me/test/2", 5: "https://t.me/test/5"}
    assert links == ["https://t.me/test/2", "https://t.me/test/5"]

    assert progress.call_count == 3
    assert progress.call_args_list[0].args == (1, 3)
    assert progress.call_args_list[1].args == (2, 3)
    assert progress.call_args_list[2].args == (3, 3)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_answer_full_scan_map_reduce_no_hits_returns_message(
    monkeypatch, sample_config, mock_logger
):
    monkeypatch.setattr(chat_answerer, "SINGLE_PASS_CONTEXT_CHAR_LIMIT", 300)
    monkeypatch.setattr(chat_answerer, "MAP_CHUNK_CONTEXT_CHAR_LIMIT", 100_000)
    monkeypatch.setattr(chat_answerer, "MAP_CHUNK_MAX_MESSAGES", 2)
    monkeypatch.setattr(chat_answerer, "MAP_CONCURRENCY_LIMIT", 1)

    answerer = ChatAnswerer(sample_config, mock_logger)
    answerer._call_llm = AsyncMock(side_effect=["", "", ""])
    answerer.answer = AsyncMock()

    messages = []
    for i in range(1, 7):
        messages.append(
            {
                "message_id": i,
                "timestamp": f"2026-01-01T00:0{i}:00",
                "sender": f"User{i}",
                "text": "x" * 120,
                "link": f"https://t.me/test/{i}",
            }
        )

    answer, index_to_link, links = await answerer.answer_full_scan(
        question="Неизвестно",
        messages=messages,
        chat_turns=[],
        channel_name="Test Channel",
    )

    assert "не нашёл сообщений" in answer.lower()
    assert index_to_link == {}
    assert links == []
    assert answerer.answer.call_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_answer_full_scan_map_reduce_provider_failures_returns_message(
    monkeypatch, sample_config, mock_logger
):
    monkeypatch.setattr(chat_answerer, "SINGLE_PASS_CONTEXT_CHAR_LIMIT", 300)
    monkeypatch.setattr(chat_answerer, "MAP_CHUNK_CONTEXT_CHAR_LIMIT", 100_000)
    monkeypatch.setattr(chat_answerer, "MAP_CHUNK_MAX_MESSAGES", 2)
    monkeypatch.setattr(chat_answerer, "MAP_CONCURRENCY_LIMIT", 1)

    answerer = ChatAnswerer(sample_config, mock_logger)
    answerer._call_llm = AsyncMock(side_effect=chat_answerer.LLMResponseError("empty"))
    answerer.answer = AsyncMock()

    messages = []
    for i in range(1, 7):
        messages.append(
            {
                "message_id": i,
                "timestamp": f"2026-01-01T00:0{i}:00",
                "sender": f"User{i}",
                "text": "x" * 120,
                "link": f"https://t.me/test/{i}",
            }
        )

    answer, index_to_link, links = await answerer.answer_full_scan(
        question="Неизвестно",
        messages=messages,
        chat_turns=[],
        channel_name="Test Channel",
    )

    assert "провайдер" in answer.lower()
    assert index_to_link == {}
    assert links == []
    assert answerer.answer.call_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_chat_answerer_uses_current_model_from_config(sample_config, mock_logger):
    sample_config.settings.openai_model = "xai/grok-2"
    answerer = ChatAnswerer(sample_config, mock_logger)

    class _Msg:
        content = "ok"

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    create = AsyncMock(return_value=_Resp())
    answerer.client.chat.completions.create = create

    await answerer.answer(question="q", context_snippets="[1] t", chat_turns=[], channel_name="c")
    assert create.call_args.kwargs["model"] == "xai/grok-2"

    sample_config.settings.openai_model = "anthropic/claude-3.5-sonnet"
    await answerer.answer(question="q2", context_snippets="[1] t", chat_turns=[], channel_name="c")
    assert create.call_args.kwargs["model"] == "anthropic/claude-3.5-sonnet"
