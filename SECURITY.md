# Security

DevAgent выполняет локальные команды от имени пользователя, поэтому security-модель v1 строится вокруг песочницы, явных ограничений tools и прозрачного хранения данных.

## Threat Model

- Модель может предложить опасную shell-команду.
- Tool output может содержать секреты или большой объём данных.
- Пользователь может случайно записать API key в config или историю.
- Docker-монтирование проекта даёт контейнеру доступ к рабочей директории.

## Controls

- Рекомендованный install запускает агента в Docker: bash-команды выполняются внутри контейнера в `/workspace`.
- `BashTool` имеет blocklist для очевидно опасных команд: `sudo`, `rm -rf /`, `mkfs`, запись в системные директории.
- `ToolRegistry` всегда пишет полный output в `.devagent/artifacts/` до truncation.
- Config хранит только имена env-переменных: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `VERCEL_TOKEN`.
- `doctor` проверяет наличие ключей, не печатая сами секреты.
- `.devagent/`, `.env`, caches и virtualenv исключены из git.

## Reporting

Пока проект приватный/ранний, сообщай уязвимости через GitHub issue с пометкой `security` без публикации секретов, логов с ключами или приватных workspace-файлов.

## Out of Scope for v1

- Полная sandbox security boundary без Docker.
- Remote execution.
- Multi-user tenancy.
- OAuth portal.
- Network egress policy внутри контейнера.
