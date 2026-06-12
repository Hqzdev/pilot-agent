# AGENTS.md

Context for AI agents working in this repository.

## Commands

- Install dev dependencies: `UV_CACHE_DIR=.uv-cache uv sync --all-groups`
- Full check: `scripts/run_tests.sh`
- Tests: `UV_CACHE_DIR=.uv-cache uv run pytest`
- Lint: `UV_CACHE_DIR=.uv-cache uv run ruff check pilot_agent tests`
- Types: `UV_CACHE_DIR=.uv-cache uv run mypy pilot_agent`
- Compile: `UV_CACHE_DIR=.uv-cache uv run python -m compileall pilot_agent`
- CLI smoke: `UV_CACHE_DIR=.uv-cache uv run python -m pilot_agent.cli --help`

## Invariants

- Session history is stored only in canonical dataclass types from `pilot_agent/agent/types.py`.
- Project state lives in `.pilot-agent/STATE.md`, not in conversational history.
- Every complete tool result is written to `.pilot-agent/artifacts/` before truncation.
- Skills are disclosed progressively: prompts get the index, full bodies load through `load_skill`.
- Secrets are never written to `config.yaml`; only environment variable names are stored.

## Quality Bar

- README and install commands must work for a new user on the first try.
- Tests must actually run through `scripts/run_tests.sh`; do not add decorative stubs.
- Errors must explain what happened and the exact command that fixes it.
- Do not commit backup files, `__pycache__`, `.DS_Store`, local caches, virtualenvs, or temp artifacts.
- Do not leave documentation that promises a feature without existing code and a test.

## Git Workflow

- Never commit directly to `main`. Each task starts from a fresh `main` branch named `feat|fix|docs|chore/kebab-case`.
- Keep PRs at or below 400 changed lines. Split larger work into multiple PRs.
- The PR title must be a conventional commit because it becomes the squashed commit on `main`.
- Delete branches after merge; auto-delete should stay enabled in GitHub.

## Anti-Scope v1

Do not add `gateway/`, `apps/`, `web/`, `locales/`, `cron/`, `plugins/`, `acp_*`, `nix/`, or `packaging/`.

Do not add embeddings, vector DBs, web UI, fullscreen TUI, subagents, schedulers,
Telegram/Discord/Slack gateways, or a native Windows installer in v1.

## Commits

Use conventional commits: `chore(scope): ...`, `feat(cli): ...`,
`fix(tools): ...`, `test(providers): ...`. Do not write `AI generated`, do not
write `admin did this`, and do not mix unrelated topics in one commit.
