# tests/test_guards.py
# dv_file_version = '261031.01'

from __future__ import annotations

import pytest

from dixpush.guards import Guards


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_guards(clock: FakeClock, **kwargs) -> Guards:
    defaults = dict(
        dedup_window_sec=60.0,
        cooldown_sec=300.0,
        rate_limit_per_minute=20,
        rate_limit_burst=5,
        clock=clock,
    )
    defaults.update(kwargs)
    return Guards(**defaults)


def test_dedup_same_key_suppressed() -> None:
    clock = FakeClock()
    g = make_guards(clock)
    assert g.allow("k") is True
    clock.advance(10)
    assert g.allow("k") is False


def test_dedup_different_keys_pass() -> None:
    clock = FakeClock()
    g = make_guards(clock)
    assert g.allow("a") is True
    assert g.allow("b") is True


def test_dedup_window_expires() -> None:
    clock = FakeClock()
    g = make_guards(clock)
    assert g.allow("k") is True
    clock.advance(61)
    # dedup истёк, но cooldown (300) ещё действует
    assert g.allow("k") is False


def test_cooldown_blocks_after_dedup() -> None:
    clock = FakeClock()
    g = make_guards(clock, rate_limit_burst=100)
    assert g.allow("k") is True
    clock.advance(120)  # dedup истёк, cooldown (300) — нет
    assert g.allow("k") is False


def test_cooldown_expires() -> None:
    clock = FakeClock()
    g = make_guards(clock, rate_limit_burst=100)
    assert g.allow("k") is True
    clock.advance(301)
    assert g.allow("k") is True


def test_rate_limit_per_key_independent() -> None:
    clock = FakeClock()
    g = make_guards(clock, dedup_window_sec=0, cooldown_sec=0, rate_limit_burst=2)
    assert g.allow("a") is True
    assert g.allow("a") is True
    assert g.allow("a") is False  # burst исчерпан по ключу "a"
    assert g.allow("b") is True  # у "b" свой счётчик


def test_rate_limit_sliding_window() -> None:
    clock = FakeClock()
    g = make_guards(clock, dedup_window_sec=0, cooldown_sec=0, rate_limit_burst=2)
    assert g.allow("k") is True
    clock.advance(10)
    assert g.allow("k") is True
    assert g.allow("k") is False
    clock.advance(55)  # первый timestamp вышел из окна 60 с
    assert g.allow("k") is True