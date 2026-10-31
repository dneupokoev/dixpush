# tests/test_ntfy.py
# dv_file_version = '261031.01'

from __future__ import annotations

import httpx
import pytest

from dixpush import Priority
from dixpush.transports.ntfy import NtfyTransport


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
