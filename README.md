<!-- README.md -->
<!-- dv_file_version = '261031.01' -->

# dixpush

Простая асинхронная библиотека push-уведомлений для Python с встроенной защитой от спама. По умолчанию использует [ntfy](https://ntfy.sh), архитектура поддерживает расширение дополнительных транспортов (email, webhook и т.д.).

## Установка

Установка напрямую с GitHub:

```bash
pip install git+https://github.com/dneupokoev/dixpush.git
```

Или зафиксируйте версию (рекомендуется для production):

```bash
pip install git+https://github.com/dneupokoev/dixpush.git@v0.1.0
```

## Быстрый старт

```python
import asyncio

from dixpush import DixPush, Priority
from dixpush.transports.ntfy import NtfyTransport


async def main() -> None:
    push = DixPush(
        transport=NtfyTransport(
            server="https://ntfy.sh",
            topics={
                "error": "error-xxxx",
                "warning": "warning-xxxx",
                "info": "info-xxxx",
            },
            token=None,  # для self-hosted с auth передайте токен
        ),
        cooldown_sec=300,
        dedup_window_sec=60,
        rate_limit_per_minute=20,
        rate_limit_burst=5,
    )

    # Позиционные аргументы
    await push.error("Telegram API", "Connection timeout", key="tg_api")

    # Именованные аргументы
    await push.warning(subj="Redis", body="Connection refused", key="redis")

    # Без key — автоматический fallback на (subj + body)[:200]
    await push.info("Daily stats", "147 запросов, 3 ошибки")

    # Переопределение приоритета
    await push.error(
        "DB down",
        "Postgres not responding",
        key="db",
        priority=Priority.URGENT,
    )

    await push.close()


asyncio.run(main())
```

## Использование из env

```python
from dixpush import DixPush

push = DixPush.from_env()
```

Переменные окружения:

```env
DIXPUSH_ENABLED=true
DIXPUSH_NTFY_SERVER=https://ntfy.sh
DIXPUSH_NTFY_TOPIC_ERROR=error-xxxx
DIXPUSH_NTFY_TOPIC_WARNING=warning-xxxx
DIXPUSH_NTFY_TOPIC_INFO=info-xxxx
DIXPUSH_NTFY_TOKEN=
DIXPUSH_COOLDOWN_SEC=300
DIXPUSH_DEDUP_WINDOW_SEC=60
DIXPUSH_RATE_LIMIT_PER_MINUTE=20
DIXPUSH_RATE_LIMIT_BURST=5
DIXPUSH_TIMEOUT_SEC=5
```

Топики `DIXPUSH_NTFY_TOPIC_*` обязательны — без них `from_env()` бросит ошибку при создании транспорта.

## Особенности

- **Защита от спама по ключу.** Дедупликация, cooldown и rate limit рассчитываются отдельно для каждого `key`. Если `key` не передан, используется `(subj + body)[:200]` в качестве автоматического ключа.
- **Сообщение = subj + body.** Заголовок отправляется через HTTP-заголовок `Title:` (в клиенте ntfy отображается жирным), тело — как основное содержимое.
- **Graceful degradation.** При недоступности ntfy логируется warning, код не падает. Ограниченный retry (1 раз), без буферизации в память.
- **Расширяемость.** Транспорт реализует ABC `Transport`, добавление email/webhook не требует изменения `push.py`.

## Уровни и приоритеты

| Метод     | Приоритет ntfy | Топик     |
|-----------|----------------|-----------|
| `error`   | `urgent` (5)   | `error`   |
| `warning` | `high` (4)     | `warning` |
| `info`    | `low` (2)      | `info`    |

`Priority` (`LOW`/`DEFAULT`/`HIGH`/`URGENT`) позволяет переопределить приоритет.

## Своя реализация транспорта

```python
from dixpush import DixPush
from dixpush.transports.base import Transport


class MyTransport(Transport):
    async def send(self, level, title, message, key, priority) -> bool:
        # ... ваша логика ...
        return True


push = DixPush(transport=MyTransport())
```

## Стек

- Python 3.10+
- Зависимость: `httpx`