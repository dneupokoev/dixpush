<!-- README.md -->
<!-- dv_file_version = '261031.04' -->

# dixpush

Простая асинхронная библиотека push-уведомлений для Python с встроенной защитой от спама. По умолчанию использует [ntfy](https://ntfy.sh), архитектура поддерживает расширение дополнительных транспортов (email, webhook и т.д.).

## Установка

Установка напрямую с GitHub:

```bash
pip install git+https://github.com/dneupokoev/dixpush.git
```

Или зафиксируйте версию (рекомендуется для production):

```bash
pip install git+https://github.com/dneupokoev/dixpush.git@v0.2.2
```

## Быстрый старт (async)

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

## Быстрый старт (sync)

Если код синхронный, используйте `*_sync`-методы. Внутри библиотека лениво поднимает фоновый event loop, задачи уходят туда, `httpx.AsyncClient` живёт в нём же. Ничего дополнительно настраивать не нужно.

```python
from dixpush import DixPush
from dixpush.transports.ntfy import NtfyTransport

push = DixPush(
    transport=NtfyTransport(
        server="https://ntfy.sh",
        topics={
            "error": "error-xxxx",
            "warning": "warning-xxxx",
            "info": "info-xxxx",
        },
    ),
)

push.error("Telegram API", "Connection timeout", key="tg_api")   # error_sync
push.warning("Redis", "Connection refused", key="redis")         # warning_sync
push.info("Daily stats", "147 запросов, 3 ошибки")               # info_sync

push.close_sync()  # остановить фоновый loop и закрыть httpx
```

### Что выбрать: async или sync

- **Async-код** (FastAPI, aiogram, воркеры) — обычные `await push.error(...)`, `await push.warning(...)`, `await push.info(...)`. Основной путь.
- **Sync-код** (Celery-таски, cron, скрипты, `def`-функции) — `push.error_sync(...)` и т.д. Не блокируют вызывающий поток, задача выполняется в фоновом loop.
- **Смешивать async- и sync-методы на одном экземпляре `DixPush` можно**, но есть нюанс: `httpx.AsyncClient` создаётся в том loop'е, где произошёл первый вызов. Если первый вызов — async (в основном loop), а потом вы зовёте `error_sync` из синхронного кода — задача уйдёт в фоновый loop, а клиент останется в основном. Это может привести к `RuntimeError` при реальном `NtfyTransport`. Для такого сценария используйте **два экземпляра** `DixPush` (один для async, один для sync) или держите все вызовы в одном стиле. `Guards` (антиспам) при этом будут раздельными — если нужен общий антиспам между async- и sync-вызовами, это отдельная задача.

## Синглтон в проекте

Один `DixPush` на процесс — иначе дедупликация, cooldown и rate limit не работают (у каждого экземпляра свои `Guards`). Удобно завести функцию в `settings.py`:

```python
# settings.py
import os
import dixpush as _dixpush_mod
from dixpush.transports.ntfy import NtfyTransport

_push: _dixpush_mod.DixPush | None = None


def dix_push() -> _dixpush_mod.DixPush:
    global _push
    if _push is None:
        _push = _dixpush_mod.DixPush(
            transport=NtfyTransport(
                server=os.getenv("DIXPUSH_NTFY_SERVER", "https://ntfy.sh"),
                topics={
                    "error":   os.getenv("DIXPUSH_NTFY_TOPIC_ERROR", ""),
                    "warning": os.getenv("DIXPUSH_NTFY_TOPIC_WARNING", ""),
                    "info":    os.getenv("DIXPUSH_NTFY_TOPIC_INFO", ""),
                },
                token=os.getenv("DIXPUSH_NTFY_TOKEN") or None,
            ),
            enabled=os.getenv("DIXPUSH_ENABLED", "true").lower() in ("1", "true", "yes", "on"),
        )
    return _push
```

Использование:

```python
# синхронно
settings.dix_push().error_sync("Telegram API", "Connection timeout", key="tg_api")

# асинхронно
await settings.dix_push().error("Telegram API", "Connection timeout", key="tg_api")
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
- **Кириллица и эмодзи в заголовке.** HTTP-заголовки должны быть ASCII, поэтому `NtfyTransport` кодирует `Title` по **RFC 2047** (через base64 без переносов строк), если в нём есть не-ASCII символы. ntfy декодирует его обратно, и вы видите исходный текст (например, `✅ 🔥 🚀 ⚠️ itzamna: стартовала`), а не `?` или «кракозябры». Это надежно работает с любыми эмодзи.
- **Graceful degradation.** При недоступности ntfy логируется warning, код не падает. Ограниченный retry (1 раз), без буферизации в память.
- **Расширяемость.** Транспорт реализует ABC `Transport`, добавление email/webhook не требует изменения `push.py`.
- **Async и sync.** `await push.error(...)` для async-кода, `push.error_sync(...)` для синхронного. Синхронный путь не требует `asyncio.run` в проекте.

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
