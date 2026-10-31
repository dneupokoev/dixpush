# src/dixpush/config.py
# dv_file_version = '261031.01'

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class DixPushConfig:
    """Конфигурация DixPush. Собирается из аргументов или env."""

    enabled: bool = True
    cooldown_sec: float = 300.0
    dedup_window_sec: float = 60.0
    rate_limit_per_minute: int = 20
    rate_limit_burst: int = 5
    timeout_sec: float = 5.0

    ntfy_server: str = "https://ntfy.sh"
    ntfy_topics: dict[str, str] = field(default_factory=dict)
    ntfy_token: str | None = None

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "DixPushConfig":
        e = os.environ if env is None else env

        def _bool(name: str, default: bool) -> bool:
            raw = e.get(name)
            if raw is None:
                return default
            return raw.strip().lower() in ("1", "true", "yes", "on")

        def _float(name: str, default: float) -> float:
            raw = e.get(name)
            if raw is None or raw == "":
                return default
            try:
                return float(raw)
            except ValueError:
                return default

        def _int(name: str, default: int) -> int:
            raw = e.get(name)
            if raw is None or raw == "":
                return default
            try:
                return int(raw)
            except ValueError:
                return default

        topics = {}
        for level in ("error", "warning", "info"):
            value = e.get(f"DIXPUSH_NTFY_TOPIC_{level.upper()}")
            if value:
                topics[level] = value

        token = e.get("DIXPUSH_NTFY_TOKEN") or None

        return cls(
            enabled=_bool("DIXPUSH_ENABLED", True),
            cooldown_sec=_float("DIXPUSH_COOLDOWN_SEC", 300.0),
            dedup_window_sec=_float("DIXPUSH_DEDUP_WINDOW_SEC", 60.0),
            rate_limit_per_minute=_int("DIXPUSH_RATE_LIMIT_PER_MINUTE", 20),
            rate_limit_burst=_int("DIXPUSH_RATE_LIMIT_BURST", 5),
            timeout_sec=_float("DIXPUSH_TIMEOUT_SEC", 5.0),
            ntfy_server=e.get("DIXPUSH_NTFY_SERVER", "https://ntfy.sh"),
            ntfy_topics=topics,
            ntfy_token=token,
        )