# tests/test_push.py
# dv_file_version = '261031.01'

from __future__ import annotations

import asyncio

import pytest

from dixpush import DixPush, Priority
from dixpush.transports.base import Transport


class MockTransport(Transport):
    def __init__(self, fail: bool = False, raise_exc: bool = False) -> None:
        self.calls: list[tuple] = []
        self.fail = fail
        self.raise_exc = raise_exc
        self.closed = False

    async def send(self, level, title, message, key, priority) -> bool:
        self.calls.append((level, title, message, key, priority))
        if self.raise_exc:
            raise RuntimeError("boom")
        return not self.fail

    async def close(self) -> None:
        self.closed = True


def make_push(transport: Transport, **kwargs) -> DixPush:
    defaults = dict(
        cooldown_sec=0,
        dedup_window_sec=0,
        rate_limit_per_minute=100,
        rate_limit_burst=100,
    )
    defaults.update(kwargs)
    return DixPush(transport=transport, **defaults)


async def _settle(push: DixPush) -> None:
    await push.close(timeout=1.0)


@pytest.mark.asyncio
async def test_error_calls_transport() -> None:
    t = MockTransport()
    push = make_push(t)
    await push.error("Subj", "Body", key="k")
    await _settle(push)
    assert t.calls == [("error", "Subj", "Body", "k", None)]


@pytest.mark.asyncio
async def test_positional_and_keyword_args() -> None:
    t = MockTransport()
    push = make_push(t)
    await push.warning("Subj", "Body", key="k1")
    await push.warning(subj="Subj2", body="Body2", key="k2")
    await _settle(push)
    assert [c[1] for c in t.calls] == ["Subj", "Subj2"]


@pytest.mark.asyncio
async def test_fallback_key_from_subj_body() -> None:
    t = MockTransport()
    push = make_push(t, dedup_window_sec=60)
    await push.info("Daily", "stats 147")
    await push.info("Daily", "stats 147")
    await _settle(push)
    assert len(t.calls) == 1


@pytest.mark.asyncio
async def test_enabled_false_skips_transport() -> None:
    t = MockTransport()
    push = make_push(t, enabled=False)
    await push.error("Subj", "Body", key="k")
    await _settle(push)
    assert t.calls == []


@pytest.mark.asyncio
async def test_priority_passed_through() -> None:
    t = MockTransport()
    push = make_push(t)
    await push.error("S", "B", key="k", priority=Priority.URGENT)
    await _settle(push)
    assert t.calls[0][4] == Priority.URGENT


@pytest.mark.asyncio
async def test_transport_exception_does_not_propagate() -> None:
    t = MockTransport(raise_exc=True)
    push = make_push(t)
    await push.error("S", "B", key="k")
    await _settle(push)  # не должно бросить


@pytest.mark.asyncio
async def test_close_closes_transport() -> None:
    t = MockTransport()
    push = make_push(t)
    await push.error("S", "B", key="k")
    await push.close()
    assert t.closed is True


@pytest.mark.asyncio
async def test_close_waits_for_pending_tasks() -> None:
    t = MockTransport()
    push = make_push(t)
    await push.error("S", "B", key="k")
    await push.close(timeout=2.0)
    assert len(t.calls) == 1
