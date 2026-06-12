# AGENTS.md

Контекст для ИИ-агентов, работающих с этим репозиторием.

## Команды

- Установка dev-зависимостей: `UV_CACHE_DIR=.uv-cache uv sync --all-groups`
- Полная проверка: `scripts/run_tests.sh`
- Тесты: `UV_CACHE_DIR=.uv-cache uv run pytest`
- Линт: `UV_CACHE_DIR=.uv-cache uv run ruff check devagent tests`
- Типы: `UV_CACHE_DIR=.uv-cache uv run mypy devagent`
- Компиляция: `UV_CACHE_DIR=.uv-cache uv run python -m compileall devagent`
- CLI smoke: `UV_CACHE_DIR=.uv-cache uv run python -m devagent.cli --help`

## Инварианты

- История сессии хранится только в канонических dataclass-типах из `devagent/agent/types.py`.
- Состояние проекта живёт в `.devagent/STATE.md`, а не в conversational history.
- Полный вывод каждого tool result сохраняется в `.devagent/artifacts/` до truncation.
- Skills раскрываются прогрессивно: в prompt идёт индекс, тело загружается через `load_skill`.
- Секреты никогда не пишутся в `config.yaml`; только имена env-переменных.

## Планка качества

- README и install-команды должны работать у чужого человека с первой попытки.
- Тесты должны реально гоняться через `scripts/run_tests.sh`; не добавлять декоративные заглушки.
- Ошибки должны объяснять, что случилось и какую команду выполнить для исправления.
- Не коммитить backup-файлы, `__pycache__`, `.DS_Store`, локальные cache/venv и временные артефакты.
- Не оставлять документацию, которая обещает фичу без существующего кода и теста.

## Анти-скоуп v1

Не добавлять `gateway/`, `apps/`, `web/`, `locales/`, `cron/`, `plugins/`, `acp_*`, `nix/`, `packaging/`.

Не добавлять embeddings, vector DB, web UI, полноэкранный TUI, subagents, scheduler, Telegram/Discord/Slack gateways или нативный Windows installer в v1.

## Git

Коммиты должны быть conventional commits: `chore(scope): ...`, `feat(cli): ...`, `fix(tools): ...`, `test(providers): ...`. Не писать `AI generated` и не смешивать разные темы в одном коммите.
