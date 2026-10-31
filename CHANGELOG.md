<!-- CHANGELOG.md -->
<!-- dv_file_version = '261031.01' -->

# Changelog

## 2026-10-31

### Добавлено
- Каркас проекта: `pyproject.toml` (hatchling, src-layout), `.gitignore`, `Pipfile`.
- `src/dixpush/transports/base.py` — абстрактный `Transport` с `async send(level, title, message, key, priority) -> bool`.
- `src/dixpush/transports/ntfy.py` — `NtfyTransport`: httpx, `Title`/`Priority` заголовки, `Authorization: Bearer`, таймаут 5 с, один retry через 1 с при 429/5xx/сетевых ошибках, graceful degradation.
- `src/dixpush/guards.py` — антиспам per-key: дедупликация, cooldown, rate limit (`dict[str, deque]`).
- `src/dixpush/push.py` — `DixPush` (`error`/`warning`/`info`), `Priority` enum, `from_env()`, `enabled`, `close()`, fire-and-forget через `asyncio.create_task()`, fallback-ключ `(subj + body)[:200]`.
- `src/dixpush/config.py` — `DixPushConfig.from_env()`.
- `src/dixpush/__init__.py` — публичный API (`DixPush`, `Priority`).
- `src/dixpush/transports/__init__.py` — реэкспорт `Transport`, `NtfyTransport`.
- Тесты: `tests/test_guards.py`, `tests/test_push.py`, `tests/test_ntfy.py`, `tests/test_config.py`.
- `README.md` — описание, установка, быстрый старт, env, расширяемость.
