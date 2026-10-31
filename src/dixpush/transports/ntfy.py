# src/dixpush/transports/ntfy.py
# dv_file_version = '261031.02'

from __future__ import annotations

import asyncio
import logging
from email.header import Header
from typing import TYPE_CHECKING

import httpx

from dixpush.transports.base import Transport

if TYPE_CHECKING:
    from dixpush.push import Priority

logger = logging.getLogger(__name__)

# Маппинг уровней на приоритеты ntfy (см. ТЗ, раздел 8)
_LEVEL_PRIORITY: dict[str, int] = {
    "error": 5,    # urgent
    "warning": 4,  # high
    "info": 2,     # low
}

# Значения Priority enum → приоритет ntfy
_PRIORITY_VALUE: dict[str, int] = {
    "LOW": 2,
    "DEFAULT": 3,
    "HIGH": 4,
    "URGENT": 5,
}


def _encode_title(title: str) -> str:
    """Кодировать Title в RFC 2047, если он не ASCII.

    ntfy декодирует encoded-word обратно в читаемый текст (эмодзи, кириллица).
    Для чистого ASCII возвращаем строку как есть.
    """
    try:
        title.encode("ascii")
        return title
    except UnicodeEncodeError:
        # RFC 2047: =?utf-8?b?...?=
        return Header(title, "utf-8").encode()


class NtfyTransport(Transport):
    """Транспорт ntfy (https://ntfy.sh или self-hosted)."""

    def __init__(
        self,
        server: str,
        topics: dict[str, str],
        token: str | None = None,
        timeout_sec: float = 5.0,
    ) -> None:
        if not topics:
            raise ValueError("topics обязательны: укажите error/warning/info")
        missing = {"error", "warning", "info"} - topics.keys()
        if missing:
            raise ValueError(f"topics: отсутствуют уровни {sorted(missing)}")

        self._server = server.rstrip("/")
        self._topics = topics
        self._token = token
        self._timeout = timeout_sec
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {}
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers=headers,
            )
        return self._client

    def _resolve_priority(self, level: str, priority: Priority | None) -> int:
        if priority is not None:
            name = getattr(priority, "name", None)
            if name and name in _PRIORITY_VALUE:
                return _PRIORITY_VALUE[name]
        return _LEVEL_PRIORITY.get(level, 3)

    async def send(
        self,
        level: str,
        title: str,
        message: str,
        key: str | None,
        priority: Priority | None,
    ) -> bool:
        topic = self._topics.get(level)
        if topic is None:
            logger.warning("NtfyTransport: неизвестный уровень %r", level)
            return False

        url = f"{self._server}/{topic}"
        headers = {
            "Title": _encode_title(title),
            "Priority": str(self._resolve_priority(level, priority)),
        }

        client = self._get_client()
        try:
            resp = await client.post(url, content=message, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            logger.warning("NtfyTransport: ошибка отправки (%s), retry", exc)
            await asyncio.sleep(1.0)
            try:
                resp = await client.post(url, content=message, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc2:
                logger.warning("NtfyTransport: повторная ошибка (%s), сдаюсь", exc2)
                return False

        if resp.status_code in (429, 500, 502, 503, 504):
            logger.warning(
                "NtfyTransport: HTTP %s, retry", resp.status_code
            )
            await asyncio.sleep(1.0)
            try:
                resp = await client.post(url, content=message, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                logger.warning("NtfyTransport: retry не удался (%s)", exc)
                return False
            if resp.status_code in (429, 500, 502, 503, 504):
                logger.warning(
                    "NtfyTransport: HTTP %s после retry, сдаюсь",
                    resp.status_code,
                )
                return False

        if not resp.is_success:
            logger.warning("NtfyTransport: HTTP %s", resp.status_code)
            return False

        return True

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None