# Contributing

Спасибо за вклад в DevAgent. Цель v1 — локальный CLI/TUI агент, который ведёт пользователя от идеи до задеплоенного MVP без web UI, gateways и лишней платформенной инфраструктуры.

## Dev Setup

```bash
./setup-dev.sh
./devagent-dev --help
```

Если `uv` ещё не установлен:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Проверки перед PR

```bash
scripts/run_tests.sh
```

Скрипт запускает ruff, mypy, pytest, compileall и CLI smoke. CI использует тот же вход, чтобы локальная и GitHub-проверка совпадали.

## PR Process

1. Держи PR маленьким и тематическим.
2. Обновляй тесты вместе с поведением.
3. Обновляй docs/examples, если меняется CLI, config или Docker UX.
4. Не добавляй секреты в config, tests или fixtures.
5. Убедись, что `scripts/run_tests.sh` зелёный.

## Conventional Commits

Используй формат:

- `chore(repo): scaffold repository structure`
- `feat(cli): add setup wizard`
- `fix(tools): enforce artifact persistence`
- `test(providers): cover malformed tool arguments`
- `docs(readme): update Docker install flow`

Сообщение должно быть коротким и конкретным. Не писать `AI generated`, `admin did this` или несколько тем в одном коммите.
