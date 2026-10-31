# src/dixpush/push.py
# dv_file_version = '261031.02'

from __future__ import annotations

import asyncio
import logging
import threading
from enum import Enum
from typing import Any, Coroutine

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
    """Асинхронная библиотека push-уведомлений с антиспамом.

    Async-методы (error/warning/info/close) — основной путь для async-кода.
    Sync-методы (error_sync/warning_sync/info_sync/close_sync) — для вызова
    из синхронного кода: задача планируется в фоновом event loop, который
    поднимается лениво при первом sync-вызове.
    """

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

        # Фоновый loop для sync-вызовов. Поднимается лениво.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._loop_lock = threading.Lock()

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

    # ------------------------------------------------------------------ async

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

    async def close(self, timeout: float = 5.0) -> None:
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=timeout)
        closer = getattr(self._transport, "close", None)
        if closer is not None:
            result = closer()
            if asyncio.iscoroutine(result):
                await result
        self._tasks.clear()

    # ------------------------------------------------------------------- sync

    def error_sync(
        self,
        subj: str,
        body: str,
        *,
        key: str | None = None,
        priority: Priority | None = None,
    ) -> None:
        """Синхронная версия error(): планирует задачу в фоновом loop."""
        self._run_sync(self.error(subj, body, key=key, priority=priority))

    def warning_sync(
        self,
        subj: str,
        body: str,
        *,
        key: str | None = None,
        priority: Priority | None = None,
    ) -> None:
        """Синхронная версия warning(): планирует задачу в фоновом loop."""
        self._run_sync(self.warning(subj, body, key=key, priority=priority))

    def info_sync(
        self,
        subj: str,
        body: str,
        *,
        key: str | None = None,
        priority: Priority | None = None,
    ) -> None:
        """Синхронная версия info(): планирует задачу в фоновом loop."""
        self._run_sync(self.info(subj, body, key=key, priority=priority))

    def close_sync(self, timeout: float = 5.0) -> None:
        """Синхронная версия close(): дожидается закрытия и останавливает loop.

        Если фоновый loop не поднимался (sync-методы не вызывались) —
        просто закрывает транспорт в текущем контексте, если есть loop,
        иначе — ничего не делает (нечего закрывать).
        """
        if self._loop is None:
            # фоновый loop не поднимался — попробуем закрыть как есть
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is not None:
                # мы внутри async-контекста — закрывать синхронно нельзя
                logger.warning(
                    "dixpush: close_sync() вызван из async-контекста без фонового loop"
                )
                return
            # нечего закрывать: transport.close() — корутина, но loop'а нет
            return

        fut = asyncio.run_coroutine_threadsafe(self.close(timeout), self._loop)
        try:
            fut.result(timeout=timeout + 1.0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("dixpush: close_sync ошибка (%s)", exc)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._loop_thread is not None:
                self._loop_thread.join(timeout=timeout + 1.0)
            self._loop = None
            self._loop_thread = None

    # --------------------------------------------------------------- internals

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """Поднять фоновый loop в отдельном потоке (один раз на экземпляр)."""
        if self._loop is not None:
            return self._loop
        with self._loop_lock:
            if self._loop is not None:
                return self._loop
            loop = asyncio.new_event_loop()
            thread = threading.Thread(
                target=loop.run_forever,
                name="dixpush-loop",
                daemon=True,
            )
            thread.start()
            self._loop = loop
            self._loop_thread = thread
            return loop

    def _run_sync(self, coro: Coroutine[Any, Any, None]) -> None:
        """Запланировать корутину в фоновом loop'е, не дожидаясь результата."""
        try:
            loop = self._ensure_loop()
        except Exception as exc:  # noqa: BLE001
            logger.warning("dixpush: не удалось поднять фоновый loop (%s)", exc)
            coro.close()
            return
        try:
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception as exc:  # noqa: BLE001
            logger.warning("dixpush: не удалось запланировать задачу (%s)", exc)
            coro.close()

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