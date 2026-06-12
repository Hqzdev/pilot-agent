# DevAgent

CLI-агент: от идеи до задеплоенного MVP за одну сессию через фазы Discovery, Planning, Coding, Deploy и Marketing.

## Demo

TODO: записать demo GIF через `vhs` или `asciinema`: `devagent setup`, `/model openrouter:qwen/qwen3-coder`, `devagent run`.

## Возможности

| Фича | Что даёт |
|---|---|
| provider-agnostic | Можно переключить модель mid-session без потери истории: канонический формат не зависит от API. |
| three-tier context | Контекст ужимается через truncation tool results, summarization и внешний `STATE.md`. |
| self-improving | Ошибки из `run_and_check` превращаются в lessons, deploy-процедуры могут стать learned skills. |
| sandboxed | В Docker-режиме bash агента выполняется внутри контейнера, а не напрямую на твоей машине. |
| verification loop | Агент не считает задачу сделанной, пока код не запустился и проверка не прошла. |

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/Muhammadcell/devagent/main/install.sh | bash
```

Windows: используй WSL2 и ту же команду внутри Linux shell.

<details>
<summary>Native uv install</summary>

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install git+https://github.com/Muhammadcell/devagent.git
```

</details>

## Getting Started

```bash
cd <папка проекта>
devagent setup          # первичная настройка, ключи не пишутся в config.yaml
devagent doctor         # диагностика окружения и провайдера
devagent init           # создаёт .devagent/STATE.md
devagent run            # старт Discovery -> Planning -> Coding -> Deploy -> Marketing
devagent status         # фаза, TODO, токены, session.jsonl
```

Docker install создаёт wrapper в `~/.local/bin/devagent`, собирает образ и монтирует текущую папку как `/workspace`. Долговременная память живёт в named volume `devagent-home`.

## CLI Reference

| Команда | Назначение |
|---|---|
| `devagent setup` | Мастер первичной настройки. |
| `devagent setup --provider X` | Setup с заранее выбранным провайдером. |
| `devagent setup --reconfigure` | Перезаписать существующий config через wizard. |
| `devagent doctor` | Диагностика окружения, конфига, инструментов, памяти и проекта. |
| `devagent doctor --json` | Машиночитаемый doctor для CI/issues. |
| `devagent update` | Обновить Docker checkout или native uv tool. |
| `devagent version` | Версия, commit hash, Python и платформа. |
| `devagent model` | Показать модели текущего провайдера. |
| `devagent model <provider>:<model>` | Переключить провайдера и модель. |
| `devagent model --list` | Таблица моделей текущего провайдера. |
| `devagent config` | Таблица config: ключ, значение, источник. |
| `devagent config set <key> <value>` | Dot-notation правка с pydantic-валидацией. |
| `devagent config get <key>` | Одно значение конфига. |
| `devagent config edit` | Открыть `config.yaml` в `$EDITOR`. |
| `devagent config path` | Напечатать путь к user config. |
| `devagent init [path]` | Создать `.devagent/STATE.md`, `session.jsonl`, `artifacts/`. |
| `devagent run` | Старт или продолжение pipeline. |
| `devagent resume` | Продолжить из `session.jsonl`. |
| `devagent status` | Текущая фаза, TODO-прогресс, токены сессии. |
| `devagent skills list` | Таблица builtin и learned skills. |
| `devagent skills show <name>` | Полный markdown скилла. |
| `devagent skills new` | Шаблон нового learned skill в `$EDITOR`. |
| `devagent lessons` | Показать `lessons.md`. |
| `devagent lessons clear` | Очистить `lessons.md` с подтверждением. |
| `devagent sessions list` | Сводка по текущей session.jsonl. |

Глобальные флаги ставятся перед командой: `--provider X`, `--model Y`, `--config <path>`, `--verbose` / `-v`, `--no-color`.

Slash-команды внутри сессии обрабатываются до LLM: `/model`, `/skip`, `/compact`, `/usage`, `/state`, `/skills`, `/undo`, `/help`, `/quit`.

## Configuration

`config.yaml` хранит только имена env-переменных, не секреты:

```yaml
provider: anthropic
model: claude-sonnet-4-6
api_key_env: ANTHROPIC_API_KEY
base_url: null
summarizer_model: null
budget_ratio: 0.7
max_turns: 200
tool_timeout_s: 120
phases:
  deploy:
    enabled: true
    vercel_token_env: VERCEL_TOKEN
  marketing:
    enabled: true
ui:
  color: auto
  show_token_counter: true
```

Приоритет значений: CLI flags, `DEVAGENT_*` env, `<project>/.devagent/config.yaml`, `~/.devagent/config.yaml`, встроенные defaults.

| Env | Использование |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic provider. |
| `OPENAI_API_KEY` | OpenAI provider. |
| `OPENROUTER_API_KEY` | OpenRouter provider. |
| `VERCEL_TOKEN` | Deploy phase через `vercel --token`. |
| `DEVAGENT_PROVIDER` | Override provider. |
| `DEVAGENT_MODEL` | Override model. |
| `DEVAGENT_BUDGET_RATIO` | Context budget ratio. |

## Design Decisions

| Решение | Почему |
|---|---|
| Канонический формат сообщений | История переносима между Anthropic, OpenAI и OpenRouter. |
| Externalized state | `STATE.md` переживает compaction и доступен пользователю. |
| Progressive skill disclosure | В prompt входит индекс, полный skill грузится только через `load_skill`. |
| Inspectable memory | Lessons и learned skills это plain markdown в `~/.devagent/`. |
| Docker sandbox | Установка проще, а bash-команды агента исполняются в контейнере. |

## Architecture

```text
user / slash command
        |
        v
CLI preflight -> config + STATE.md + skills index + lessons
        |
        v
ContextManager.prepare(history)
        |
        v
Provider.complete(system, canonical messages, tool specs)
        |
        v
AgentLoop logs assistant message -> ToolRegistry executes calls
        |
        v
full tool output -> .devagent/artifacts -> truncated result to model
        |
        v
STATE.md / session.jsonl / lessons.md
```

## Development

```bash
./setup-dev.sh
UV_CACHE_DIR=.uv-cache uv run pytest
UV_CACHE_DIR=.uv-cache uv run ruff check devagent tests
UV_CACHE_DIR=.uv-cache uv run mypy devagent
```

## Contributing

Коммиты держи маленькими и тематическими, в conventional commits: `fix(cli): ...`, `test(onboarding): ...`, `docs(readme): ...`.

## License

MIT
