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
from dixpush import DixPush, Priority
from dixpush.transports.ntfy import NtfyTransport

push = DixPush(
    transport=NtfyTransport(
        server="https://ntfy.sh",
        topics={"error": "error-xxxx", "warning": "warning-xxxx", "info": "info-xxxx"},
        token=None,  # при использовании self-hosted с auth передайте токен
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
await push.error("DB down", "Postgres not responding", key="db", priority=Priority.URGENT)

await push.close()
```

## Особенности

- **Защита от спама по ключу**: дедупликация, cooldown, rate limit рассчитываются отдельно для каждого `key`. Если `key` не передан, используется `(subj + body)[:200]` в качестве автоматического ключа.
- **Сообщение = subj + body**: заголовок отправляется через HTTP-заголовок `Title:` (в клиенте ntfy отображается жирным), тело — как основное содержимое.
- **Graceful degradation**: при недоступности ntfy логируется warning, код не падает. Ограниченный retry (1 раз), без буферизации в память.
- **Расширяемость**: транспорт реализует ABC `Transport`, добавление email/webhook не требует изменения `push.py`.

## Переменные окружения

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
```

Используйте `DixPush.from_env()` для автоматического создания транспорта из env.

## Стек

- Python 3.10+
- Зависимость: `httpx`
