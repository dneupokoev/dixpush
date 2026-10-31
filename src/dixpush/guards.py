# src/dixpush/guards.py
# dv_file_version = '261031.01'

from __future__ import annotations

import time
from collections import deque


class Guards:
    """Антиспам по эффективному ключу.

    Все три проверки (dedup, cooldown, rate limit) — per-key.
    Ключ рассчитывается в DixPush: key или (subj + body)[:200].
    """

    def __init__(
        self,
        dedup_window_sec: float = 60.0,
        cooldown_sec: float = 300.0,
        rate_limit_per_minute: int = 20,
        rate_limit_burst: int = 5,
        clock: callable = time.monotonic,
    ) -> None:
        self._dedup_window = dedup_window_sec
        self._cooldown = cooldown_sec
        self._rate_per_minute = rate_limit_per_minute
        self._rate_burst = rate_limit_burst
        self._clock = clock

        self._dedup: dict[str, float] = {}
        self._cooldown_map: dict[str, float] = {}
        self._rate: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        """Проверить, можно ли отправить. При True — записать факт отправки.

        Возвращает False, если уведомление подавлено (молча return).
        """
        now = self._clock()

        last_dedup = self._dedup.get(key)
        if last_dedup is not None and now - last_dedup < self._dedup_window:
            return False

        last_cooldown = self._cooldown_map.get(key)
        if last_cooldown is not None and now - last_cooldown < self._cooldown:
            return False

        bucket = self._rate.get(key)
        if bucket is None:
            bucket = deque()
            self._rate[key] = bucket
        while bucket and now - bucket[0] >= 60.0:
            bucket.popleft()
        if len(bucket) >= self._rate_burst:
            return False

        # Все проверки пройдены — фиксируем отправку
        self._dedup[key] = now
        self._cooldown_map[key] = now
        bucket.append(now)
        return True