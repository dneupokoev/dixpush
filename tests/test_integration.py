# tests/test_integration.py
# dv_file_version = '261031.01'

from __future__ import annotations

import pytest

from dixpush import DixPush, Priority
from dixpush.transports.ntfy import NtfyTransport


class RecordingTransport(NtfyTransport):
    """NtfyTransport с перехватом HTTP через httpx.MockTransport."""

    def __init__(self, handler, **kwargs) -> None:
        super().__init__(
            server="https://ntfy.example.com",
            topics={"error": "e", "warning": "w", "info": "i"},
            token=None,
            timeout_sec=0.5,
            **kwargs,
        )
        import httpx

        self._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=0.5,
        )


@pytest.mark.asyncio
async def test_end_to_end_dedup_by_key() -> None:
    import httpx

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    transport = RecordingTransport(handler)
    push = DixPush(
        transport=transport,
        dedup_window_sec=60,
        cooldown_sec=0,
        rate_limit_burst=100,
    )

    await push.error("Subj", "Body", key="k")
    await push.error("Subj", "Body", key="k")  # подавлено dedup
    await push.close()

    assert len(calls) == 1
    assert calls[0].headers["Title"] == "Subj"
    assert calls[0].content.decode() == "Body"


@pytest.mark.asyncio
async def test_end_to_end_different_levels_routing() -> None:
    import httpx

    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200)

    transport = RecordingTransport(handler)
    push = DixPush(
        transport=transport,
        dedup_window_sec=0,
        cooldown_sec=0,
        rate_limit_burst=100,
    )

    await push.error("E", "e", key="k1")
    await push.warning("W", "w", key="k2")
    await push.info("I", "i", key="k3")
    await push.close()

    assert urls == [
        "https://ntfy.example.com/e",
        "https://ntfy.example.com/w",
        "https://ntfy.example.com/i",
    ]


@pytest.mark.asyncio
async def test_end_to_end_disabled_skips_http() -> None:
    import httpx

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    transport = RecordingTransport(handler)
    push = DixPush(transport=transport, enabled=False)

    await push.error("S", "B", key="k")
    await push.close()

    assert calls == []


@pytest.mark.asyncio
async def test_end_to_end_priority_override() -> None:
    import httpx

    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["priority"] = request.headers["Priority"]
        return httpx.Response(200)

    transport = RecordingTransport(handler)
    push = DixPush(
        transport=transport,
        dedup_window_sec=0,
        cooldown_sec=0,
        rate_limit_burst=100,
    )

    await push.info("S", "B", key="k", priority=Priority.URGENT)
    await push.close()

    assert captured["priority"] == "5"
