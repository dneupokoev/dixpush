<!-- CHANGELOG.md -->
<!-- dv_file_version = '261031.02' -->

# Changelog

## 2026-10-31

### Добавлено
- `src/dixpush/push.py` — sync-обёртки `error_sync()` / `warning_sync()` / `info_sync()` / `close_sync()` для вызова из синхронного кода. Внутри — лениво поднимаемый фоновый event loop (один на экземпляр `DixPush`), задачи планируются через `asyncio.run_coroutine_threadsafe()`. Async-методы (`error`/`warning`/`info`/`close`) не изменены — обратная совместимость полная.
- `tests/test_push.py` — тесты на `*_sync`: вызов транспорта, priority, dedup по `key`, `enabled=False`, `close_sync` без фонового loop'а, смешивание async+sync с общим `Guards`.
- `README.md` — разделы «Быстрый старт (sync)», «Что выбрать: async или sync», «Синглтон в проекте» (`settings.dix_push()`).

### Изменено
- `src/dixpush/push.py` — `dv_file_version` → `'261031.02'`, добавлены импорты `threading`, `Coroutine`; в `__init__` — поля `_loop`, `_loop_thread`, `_loop_lock`; приватные `_ensure_loop()` и `_run_sync()`.
- `README.md` — `dv_file_version` → `'261031.02'`, версия в команде установки → `@v0.2.0`.
- `tests/test_push.py` — `dv_file_version` → `'261031.02'`, `MockTransport` получил `threading.Lock` (sync-вызовы идут из фонового потока), добавлен хелпер `_wait_calls()`.

### Исправлено
- Нет.

### Удалено
- Нет.

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
- Тесты: `tests/test_guards.py`, `tests/test_push.py`, `tests/test_ntfy.py`, `tests/test_config.py`, `tests/test_integration.py`.
- `README.md` — описание, установка, быстрый старт, env, расширяемость.
- `AGENTS.md` — инструкция для ИИ-ассистентов.