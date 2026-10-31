# tests/test_config.py
# dv_file_version = '261031.01'

from __future__ import annotations

from dixpush.config import DixPushConfig


def test_from_env_defaults_when_empty() -> None:
    cfg = DixPushConfig.from_env(env={})
    assert cfg.enabled is True
    assert cfg.cooldown_sec == 300.0
    assert cfg.dedup_window_sec == 60.0
    assert cfg.rate_limit_per_minute == 20
    assert cfg.rate_limit_burst == 5
    assert cfg.timeout_sec == 5.0
    assert cfg.ntfy_server == "https://ntfy.sh"
    assert cfg.ntfy_topics == {}
    assert cfg.ntfy_token is None


def test_from_env_reads_values() -> None:
    env = {
        "DIXPUSH_ENABLED": "false",
        "DIXPUSH_NTFY_SERVER": "https://ntfy.example.com",
        "DIXPUSH_NTFY_TOPIC_ERROR": "e-xyz",
        "DIXPUSH_NTFY_TOPIC_WARNING": "w-xyz",
        "DIXPUSH_NTFY_TOPIC_INFO": "i-xyz",
        "DIXPUSH_NTFY_TOKEN": "tk_1",
        "DIXPUSH_COOLDOWN_SEC": "10",
        "DIXPUSH_DEDUP_WINDOW_SEC": "5",
        "DIXPUSH_RATE_LIMIT_PER_MINUTE": "7",
        "DIXPUSH_RATE_LIMIT_BURST": "3",
        "DIXPUSH_TIMEOUT_SEC": "2.5",
    }
    cfg = DixPushConfig.from_env(env=env)
    assert cfg.enabled is False
    assert cfg.ntfy_server == "https://ntfy.example.com"
    assert cfg.ntfy_topics == {
        "error": "e-xyz",
        "warning": "w-xyz",
        "info": "i-xyz",
    }
    assert cfg.ntfy_token == "tk_1"
    assert cfg.cooldown_sec == 10.0
    assert cfg.dedup_window_sec == 5.0
    assert cfg.rate_limit_per_minute == 7
    assert cfg.rate_limit_burst == 3
    assert cfg.timeout_sec == 2.5


def test_from_env_invalid_values_fall_back() -> None:
    env = {
        "DIXPUSH_COOLDOWN_SEC": "abc",
        "DIXPUSH_RATE_LIMIT_BURST": "xyz",
        "DIXPUSH_ENABLED": "maybe",
    }
    cfg = DixPushConfig.from_env(env=env)
    assert cfg.cooldown_sec == 300.0
    assert cfg.rate_limit_burst == 5
    assert cfg.enabled is False  # "maybe" не входит в true-набор


def test_from_env_partial_topics() -> None:
    env = {"DIXPUSH_NTFY_TOPIC_ERROR": "only-error"}
    cfg = DixPushConfig.from_env(env=env)
    assert cfg.ntfy_topics == {"error": "only-error"}
