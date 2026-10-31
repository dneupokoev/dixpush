# src/dixpush/transports/base.py
# dv_file_version = '261031.01'

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dixpush.push import Priority


class Transport(ABC):
    """Абстрактный транспорт для отправки уведомлений.

    Реализации (NtfyTransport, EmailTransport и т.д.) наследуют этот класс
    и переопределяют send(). Ядро (DixPush) не знает о конкретном транспорте.
    """

    @abstractmethod
    async def send(
        self,
        level: str,
        title: str,
        message: str,
        key: str | None,
        priority: Priority | None,
    ) -> bool:
        """Отправить одно уведомление.

        Args:
            level: Уровень уведомления — "error", "warning" или "info".
            title: Заголовок (subj), отображается выделенным в клиенте.
            message: Тело сообщения (body).
            key: Эффективный ключ антиспама (уже рассчитан в DixPush).
            priority: Переопределение приоритета; None — дефолт по уровню.

        Returns:
            True, если отправка успешна, иначе False.
            Реализация не должна пробрасывать исключения наружу —
            при недоступности сервера логировать warning и возвращать False.
        """
        ...