import pytest

from src.bot_commands import BotCommandHandler


@pytest.mark.unit
def test_apply_citation_sources_keeps_only_cited_links():
    index_to_link = {1: "https://t.me/test/1", 2: "https://t.me/test/2", 3: "https://t.me/test/3"}
    answer = "В сообщениях упоминается имя Ирина как пример имени помощника. [2]"

    out = BotCommandHandler._apply_citation_sources(
        answer=answer, index_to_link=index_to_link, links=list(index_to_link.values())
    )

    assert "Источники:" in out
    assert "- [2] https://t.me/test/2" in out
    assert "https://t.me/test/1" not in out
    assert "https://t.me/test/3" not in out


@pytest.mark.unit
def test_apply_citation_sources_replaces_existing_sources_block():
    index_to_link = {1: "https://t.me/test/1", 2: "https://t.me/test/2"}
    answer = "Тут факт. [1]\n\nИсточники:\n- [99] https://bad\n- [1] https://also-bad"

    out = BotCommandHandler._apply_citation_sources(
        answer=answer, index_to_link=index_to_link, links=list(index_to_link.values())
    )

    assert "- [1] https://t.me/test/1" in out
    assert "https://bad" not in out
    assert "https://also-bad" not in out


@pytest.mark.unit
def test_apply_citation_sources_falls_back_when_no_citations():
    index_to_link = {1: "https://t.me/test/1", 2: "https://t.me/test/2"}
    answer = "Не могу уверенно сослаться на конкретный пост."

    out = BotCommandHandler._apply_citation_sources(
        answer=answer, index_to_link=index_to_link, links=list(index_to_link.values())
    )

    assert "Источники (возможные):" in out
    assert "https://t.me/test/1" in out


@pytest.mark.unit
def test_apply_citation_sources_html_makes_bold_links():
    index_to_link = {1: "https://t.me/test/1", 2: "https://t.me/test/2"}
    answer = "Факт из сообщения. [2]"

    out = BotCommandHandler._apply_citation_sources_html(
        answer=answer, index_to_link=index_to_link, links=list(index_to_link.values())
    )

    assert '<a href="https://t.me/test/2">[2]</a>' in out
    assert "<b>" in out
    assert "Источники" in out
    assert "https://t.me/test/2" in out
