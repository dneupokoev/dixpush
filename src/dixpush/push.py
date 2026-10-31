# src/dixpush/push.py
# dv_file_version = '261031.01'

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any

from dixpush.config import DixPushConfig
from dixpush.guards import Guards
from dixpush.transports.base import Transport
from dixpush.transports.ntfy import NtfyTransport

logger = logging.getLogger(__name__)

_FALLBACK_KEY_LEN = 200


class Priority(Enum):
    """Приоритет уведомления (переопределяет дефолт по уровню)."""

    LOW = 2
    DEFAULT = 3
    HIGH = 4
    URGENT = 5


class DixPush:
    """Асинхронная библиотека push-уведомлений с антиспамом."""

    def __init__(
        self,
        transport: Transport,
        cooldown_sec: float = 300.0,
        dedup_window_sec: float = 60.0,
        rate_limit_per_minute: int = 20,
        rate_limit_burst: int = 5,
        enabled: bool = True,
    ) -> None:
        self._transport = transport
        self._enabled = enabled
        self._guards = Guards(
            dedup_window_sec=dedup_window_sec,
            cooldown_sec=cooldown_sec,
            rate_limit_per_minute=rate_limit_per_minute,
            rate_limit_burst=rate_limit_burst,
        )
        self._tasks: set[asyncio.Task[Any]] = set()

    @classmethod
    def from_env(cls) -> "DixPush":
        cfg = DixPushConfig.from_env()
        transport = NtfyTransport(
            server=cfg.ntfy_server,
            topics=cfg.ntfy_topics,
            token=cfg.ntfy_token,
            timeout_sec=cfg.timeout_sec,
        )
        return cls(
            transport=transport,
            cooldown_sec=cfg.cooldown_sec,
            dedup_window_sec=cfg.dedup_window_sec,
            rate_limit_per_minute=cfg.rate_limit_per_minute,
            rate_limit_burst=cfg.rate_limit_burst,
            enabled=cfg.enabled,
        )

    async def error(
        self,
        subj: str,
        body: str,
        *,
        key: str | None = None,
        priority: Priority | None = None,
    ) -> None:
        await self._dispatch("error", subj, body, key, priority)

    async def warning(
        self,
        subj: str,
        body: str,
        *,
        key: str | None = None,
        priority: Priority | None = None,
    ) -> None:
        await self._dispatch("warning", subj, body, key, priority)

    async def info(
        self,
        subj: str,
        body: str,
        *,
        key: str | None = None,
        priority: Priority | None = None,
    ) -> None:
        await self._dispatch("info", subj, body, key, priority)

    async def _dispatch(
        self,
        level: str,
        subj: str,
        body: str,
        key: str | None,
        priority: Priority | None,
    ) -> None:
        if not self._enabled:
            return

        effective_key = key if key is not None else (subj + body)[:_FALLBACK_KEY_LEN]
        if not self._guards.allow(effective_key):
            return

        task = asyncio.create_task(
            self._send_safe(level, subj, body, effective_key, priority)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _send_safe(
        self,
        level: str,
        subj: str,
        body: str,
        key: str,
        priority: Priority | None,
    ) -> None:
        try:
            ok = await self._transport.send(level, subj, body, key, priority)
            if not ok:
                logger.warning("dixpush: отправка не удалась (level=%s)", level)
        except Exception as exc:  # noqa: BLE001 — не роняем вызывающий код
            logger.warning("dixpush: исключение при отправке (%s)", exc)

    async def close(self, timeout: float = 5.0) -> None:
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=timeout)
        closer = getattr(self._transport, "close", None)
        if closer is not None:
            result = closer()
            if asyncio.iscoroutine(result):
                await result
        self._tasks.clear()