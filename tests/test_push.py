# tests/test_push.py
# dv_file_version = '261031.02'

from __future__ import annotations

import threading
import time

import pytest

from dixpush import DixPush, Priority
from dixpush.transports.base import Transport


class MockTransport(Transport):
    def __init__(self, fail: bool = False, raise_exc: bool = False) -> None:
        self.calls: list[tuple] = []
        self.fail = fail
        self.raise_exc = raise_exc
        self.closed = False
        self._lock = threading.Lock()

    async def send(self, level, title, message, key, priority) -> bool:
        with self._lock:
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


def _wait_calls(transport: MockTransport, n: int, timeout: float = 2.0) -> None:
    """Дождаться, пока транспорт получит n вызовов (для *_sync)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with transport._lock:
            if len(transport.calls) >= n:
                return
        time.sleep(0.01)
    with transport._lock:
        raise AssertionError(
            f"ожидали {n} вызовов, получили {len(transport.calls)}"
        )


# --------------------------------------------------------------- async-методы

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


# ---------------------------------------------------------------- sync-методы

def test_error_sync_calls_transport() -> None:
    t = MockTransport()
    push = make_push(t)
    push.error_sync("Subj", "Body", key="k")
    _wait_calls(t, 1)
    push.close_sync()
    assert t.calls == [("error", "Subj", "Body", "k", None)]
    assert t.closed is True


def test_warning_sync_and_info_sync() -> None:
    t = MockTransport()
    push = make_push(t)
    push.warning_sync("W", "w", key="k1")
    push.info_sync("I", "i", key="k2")
    _wait_calls(t, 2)
    push.close_sync()
    levels = sorted(c[0] for c in t.calls)
    assert levels == ["info", "warning"]


def test_sync_priority_passed_through() -> None:
    t = MockTransport()
    push = make_push(t)
    push.error_sync("S", "B", key="k", priority=Priority.URGENT)
    _wait_calls(t, 1)
    push.close_sync()
    assert t.calls[0][4] == Priority.URGENT


def test_sync_dedup_by_key() -> None:
    t = MockTransport()
    push = make_push(t, dedup_window_sec=60)
    push.error_sync("S", "B", key="k")
    push.error_sync("S", "B", key="k")  # подавлено dedup
    _wait_calls(t, 1)
    time.sleep(0.1)  # дать время второй задаче (если бы прошла)
    push.close_sync()
    assert len(t.calls) == 1


def test_sync_enabled_false_skips_transport() -> None:
    t = MockTransport()
    push = make_push(t, enabled=False)
    push.error_sync("S", "B", key="k")
    time.sleep(0.1)
    push.close_sync()
    assert t.calls == []


def test_close_sync_without_loop_is_safe() -> None:
    """close_sync без предшествующих sync-вызовов не должен падать."""
    t = MockTransport()
    push = make_push(t)
    push.close_sync()  # фоновый loop не поднимался — no-op
    assert t.calls == []


def test_sync_and_async_mix_dedup() -> None:
    """Guards общий на экземпляр: async-вызов и sync-вызов с одним key — один отправлен."""
    t = MockTransport()
    push = make_push(t, dedup_window_sec=60)

    import asyncio

    async def _run_async() -> None:
        await push.error("S", "B", key="k")
        push.error_sync("S", "B", key="k")  # подавлено dedup

    asyncio.run(_run_async())
    time.sleep(0.1)
    push.close_sync()
    assert len(t.calls) == 1