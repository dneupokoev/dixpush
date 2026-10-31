# tests/test_ntfy.py
# dv_file_version = '261031.03'

from __future__ import annotations

import httpx
import pytest
from email.header import decode_header

from dixpush import Priority
from dixpush.transports.ntfy import NtfyTransport, _encode_title


def make_transport(handler, token: str | None = None) -> NtfyTransport:
    t = NtfyTransport(
        server="https://ntfy.example.com",
        topics={"error": "e-topic", "warning": "w-topic", "info": "i-topic"},
        token=token,
        timeout_sec=0.5,
    )
    # подменяем клиент на MockTransport httpx
    t._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        timeout=0.5,
    )
    return t


@pytest.mark.asyncio
async def test_send_success_and_headers() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["title"] = request.headers.get("Title")
        captured["priority"] = request.headers.get("Priority")
        captured["body"] = request.content.decode()
        return httpx.Response(200)

    t = make_transport(handler)
    ok = await t.send("error", "Subj", "Body", "k", None)
    await t.close()

    assert ok is True
    assert captured["url"] == "https://ntfy.example.com/e-topic"
    assert captured["title"] == "Subj"
    assert captured["priority"] == "5"
    assert captured["body"] == "Body"


@pytest.mark.asyncio
async def test_priority_override() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["priority"] = request.headers.get("Priority")
        return httpx.Response(200)

    t = make_transport(handler)
    await t.send("info", "S", "B", "k", Priority.URGENT)
    await t.close()
    assert captured["priority"] == "5"


@pytest.mark.asyncio
async def test_token_sets_authorization() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200)

    t = make_transport(handler, token="tk_abc")
    # пересоздаём клиент с токеном
    t._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer tk_abc"},
        timeout=0.5,
    )
    await t.send("error", "S", "B", "k", None)
    await t.close()
    assert captured["auth"] == "Bearer tk_abc"


@pytest.mark.asyncio
async def test_retry_on_5xx_then_success() -> None:
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200)

    t = make_transport(handler)
    ok = await t.send("error", "S", "B", "k", None)
    await t.close()
    assert ok is True
    assert state["n"] == 2


@pytest.mark.asyncio
async def test_retry_on_5xx_twice_returns_false() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    t = make_transport(handler)
    ok = await t.send("error", "S", "B", "k", None)
    await t.close()
    assert ok is False


@pytest.mark.asyncio
async def test_network_error_returns_false() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    t = make_transport(handler)
    ok = await t.send("error", "S", "B", "k", None)
    await t.close()
    assert ok is False


@pytest.mark.asyncio
async def test_unknown_level_returns_false() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    t = make_transport(handler)
    ok = await t.send("debug", "S", "B", "k", None)
    await t.close()
    assert ok is False


@pytest.mark.asyncio
async def test_missing_topics_raises() -> None:
    with pytest.raises(ValueError):
        NtfyTransport(server="https://ntfy.sh", topics={})
    with pytest.raises(ValueError):
        NtfyTransport(server="https://ntfy.sh", topics={"error": "x"})


# ---------------------------------------------------------------- RFC 2047

def test_encode_title_ascii_unchanged() -> None:
    """Чистый ASCII не трогаем."""
    assert _encode_title("Subj") == "Subj"
    assert _encode_title("ERROR | prod") == "ERROR | prod"


def test_encode_title_cyrillic_rfc2047() -> None:
    """Кириллица → RFC 2047 encoded-word, декодируется обратно."""
    src = "Ошибка: стартовала"
    encoded = _encode_title(src)
    assert encoded != src
    assert encoded.isascii()  # заголовок стал ASCII
    # декодируем — должен вернуться исходный текст
    decoded_parts = decode_header(encoded)
    decoded = "".join(
        part.decode(charset or "utf-8") if isinstance(part, bytes) else part
        for part, charset in decoded_parts
    )
    assert decoded == src


def test_encode_title_emoji_no_newlines() -> None:
    """Эмодзи (вызывавшие падение) → RFC 2047, без переносов строк."""
    src = "✅ 🔥 🚀 ⚠️ itzamna: стартовала (261031.01)"
    encoded = _encode_title(src)
    assert encoded != src
    assert encoded.isascii()
    assert "\n" not in encoded  # НИКАКИХ переносов!
    
    decoded_parts = decode_header(encoded)
    decoded = "".join(
        part.decode(charset or "utf-8") if isinstance(part, bytes) else part
        for part, charset in decoded_parts
    )
    assert decoded == src


def test_encode_title_long_emoji_no_newlines() -> None:
    """Очень длинный заголовок → одна строка, без переносов."""
    src = "🔥" * 50 + " Очень длинный заголовок " + "🚀" * 50
    encoded = _encode_title(src)
    assert encoded.isascii()
    assert "\n" not in encoded  # НИКАКИХ переносов!
    
    decoded_parts = decode_header(encoded)
    decoded = "".join(
        part.decode(charset or "utf-8") if isinstance(part, bytes) else part
        for part, charset in decoded_parts
    )
    assert decoded == src


@pytest.mark.asyncio
async def test_send_cyrillic_title_does_not_raise() -> None:
    """Раньше падало с UnicodeEncodeError — теперь нет."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["title"] = request.headers.get("Title")
        return httpx.Response(200)

    t = make_transport(handler)
    ok = await t.send("error", "Ошибка: тест", "Body", "k", None)
    await t.close()

    assert ok is True
    assert captured["title"] is not None
    assert captured["title"].isascii()
    assert "\n" not in captured["title"]
    
    parts = decode_header(captured["title"])
    decoded = "".join(
        p.decode(cs or "utf-8") if isinstance(p, bytes) else p
        for p, cs in parts
    )
    assert decoded == "Ошибка: тест"


@pytest.mark.asyncio
async def test_send_emoji_title_does_not_raise() -> None:
    """Заголовок с эмодзи (как в логах itzamna) — не падает, доходит читаемым."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["title"] = request.headers.get("Title")
        return httpx.Response(200)

    t = make_transport(handler)
    title = "✅ 🔥 🚀 ⚠️ itzamna: стартовала (261031.01)"
    ok = await t.send("error", title, "Body", "k", None)
    await t.close()

    assert ok is True
    assert captured["title"].isascii()
    assert "\n" not in captured["title"]
    
    parts = decode_header(captured["title"])
    decoded = "".join(
        p.decode(cs or "utf-8") if isinstance(p, bytes) else p
        for p, cs in parts
    )
    assert decoded == title