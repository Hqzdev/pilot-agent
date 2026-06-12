# DevAgent ⚙

**From idea to deployed MVP — one terminal session.**

[![CI](https://github.com/Muhammadcell/devagent/actions/workflows/ci.yml/badge.svg)](https://github.com/Muhammadcell/devagent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)
[![Ruff](https://img.shields.io/badge/lint-ruff-46a2f1.svg)](https://github.com/astral-sh/ruff)

DevAgent is a local CLI agent that takes a product idea through discovery,
planning, coding, deployment, and launch copy in one guided session. It doesn't
consider a task done until the code actually runs through the built-in
verification loop, and it keeps project state outside the chat in `STATE.md`.
Lessons and learned skills persist across projects as plain markdown you can
read and edit.

Use Anthropic, OpenAI, or OpenRouter. The core history format is provider
agnostic, so `/model` can switch providers mid-session without throwing away
the conversation.

## Capabilities

| Feature | Description |
|---|---|
| A real terminal interface | Multiline editing, slash-command autocomplete, input history, interrupt handling, and collapsed tool output. |
| Verification loop | The agent runs what it writes, reads stderr, and fixes; a task is not complete until the check passes. |
| A learning loop | Lessons from fix cycles, deploy skill synthesis, skill scoring, and plain markdown memory under `~/.devagent/`. |
| Provider-agnostic core | Canonical dataclass messages under the hood; provider conversion happens only at API call time. |
| Sandboxed by default | Agent commands can execute in a per-session Docker sandbox; local backend is available when explicitly selected. |
| Three-tier context | Tool-output truncation, LLM summarization, and externalized project state in `.devagent/STATE.md`. |

## Quick Install

### Linux, macOS, WSL2

```bash
curl -fsSL https://raw.githubusercontent.com/Muhammadcell/devagent/main/install.sh | bash
```

The installer detects Docker and prepares the sandboxed backend. No Docker? It
falls back to a native install via `uv` and tells you before running commands
locally.

<details><summary>Windows (native)</summary>

Native Windows is planned for v1.1. WSL2 works today with the command above.

</details>

<details><summary>Manual install (uv)</summary>

```bash
uv tool install git+https://github.com/Muhammadcell/devagent
```

</details>

After installation:

```bash
devagent setup    # 1-minute wizard: provider, key, model, sandbox, tools
cd your-project && devagent init && devagent run
```

## Getting Started

```bash
devagent              # start / continue a session in the current project
devagent setup        # full setup wizard: provider, keys, sandbox, tools
devagent model        # choose your LLM provider and model
devagent model <provider>:<model>
devagent tools        # enable/configure web search, fetch, and deploy tools
devagent backend      # choose where agent commands run: docker or local
devagent doctor       # diagnose config, provider, tools, backend, and project state
devagent lessons clear
devagent update       # update to the latest version
```

## Slash Commands

| Action | Command |
|---|---|
| Change model mid-session | `/model [provider:model]` |
| Skip to next phase | `/skip` |
| Compress context / check usage | `/compact`, `/usage` |
| Show project state | `/state` |
| Browse skills | `/skills` |
| Undo last turn | `/undo` |
| Interrupt current work | `Ctrl+C` or type a new instruction |

## How It Works

DevAgent runs a five-phase pipeline:

1. **Discovery** asks focused product questions and writes the brief.
2. **Planning** writes the file map, schema notes, and TODO list to `STATE.md`.
3. **Coding** takes one TODO at a time, edits files, and runs verification.
4. **Deploy** uses the Vercel skill and checks the production URL.
5. **Marketing** generates README structure, Reddit launch copy, and landing copy.

```text
user input
  ↓
phase prompt + STATE.md + skill index + lessons
  ↓
ContextManager.prepare(history)
  ↓
Provider.complete(system, canonical messages, tool specs)
  ↓
AgentLoop logs assistant message
  ↓
ToolRegistry executes calls through the selected backend
  ↓
full tool output → .devagent/artifacts/
truncated result → model context
  ↓
STATE.md / session.jsonl / lessons.md
```

## Documentation

| Section | What's Covered |
|---|---|
| [Quickstart](docs/quickstart.md) | Setup, first project, first run. |
| [Configuration](docs/configuration.md) | Config precedence, env variables, credentials, recommendations. |
| [CLI Reference](docs/cli-reference.md) | Commands, slash commands, setup, model, tools, backend. |
| [Skills System](docs/skills.md) | Builtin skills, learned skills, scoring, progressive disclosure. |
| [Memory](docs/memory.md) | Lessons, skill synthesis, markdown memory files. |
| [Architecture](docs/architecture.md) | Canonical messages, context manager, loop, providers. |
| [Docker & Sandbox](docs/docker.md) | Native CLI plus Docker execution backend. |
| [Contributing](CONTRIBUTING.md) | Development setup and PR conventions. |

## Design Decisions

**Canonical message format.** Session history is stored only as internal
dataclasses. Anthropic/OpenAI/OpenRouter formatting happens at the API boundary,
which makes mid-session provider switching possible.

**`STATE.md` over chat memory.** Long-running project state lives in
`.devagent/STATE.md`, not in fragile conversational memory. The model sees it
every turn and updates it after meaningful work.

**Progressive skill disclosure.** The system prompt gets only the skill index.
Full skill bodies are loaded on demand with `load_skill`, keeping context small
until a procedure is actually needed.

**Inspectable markdown memory.** Lessons and learned skills are normal markdown
files under `~/.devagent/`. Users can inspect, edit, delete, and version them
without a database or opaque embedding store.

**Sandbox by default.** The CLI runs natively for a clean terminal experience,
while agent-owned shell commands can run in a Docker sandbox container. The
local backend exists for speed and constrained environments.

## Contributing

```bash
git clone https://github.com/Muhammadcell/devagent.git
cd devagent
./setup-dev.sh
./devagent --help
```

Manual path:

```bash
uv sync --all-groups --frozen
.venv/bin/ruff check devagent tests
.venv/bin/mypy --no-incremental --no-sqlite-cache devagent
.venv/bin/pytest
```

Use conventional commits such as `feat(cli): add backend selector`,
`test(tools): cover web fetch ssrf guard`, or `docs(readme): refresh setup`.

## License

MIT — see [LICENSE](LICENSE).

Built by the DevAgent contributors:
[Muhammadcell](https://github.com/Muhammadcell),
[Ha1zyy](https://github.com/Ha1zyy), and
[abdulluda3](https://github.com/abdulluda3).
