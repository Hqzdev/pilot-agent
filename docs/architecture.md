# Architecture

Pilot Agent is a local Typer CLI around a phase-based agent loop.

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
ToolRegistry executes calls through selected backend
  ↓
full tool output → .pilot-agent/artifacts/
truncated result → model context
  ↓
STATE.md / session.jsonl / lessons.md
```

Key modules:

| Module | Responsibility |
|---|---|
| `pilot_agent/cli/main.py` | Typer app, command preflight, config/auth/model commands. |
| `pilot_agent/agent/loop.py` | Phase loop, slash commands, tool dispatch, phase transitions. |
| `pilot_agent/agent/context.py` | Context budgeting, compaction, session artifact references. |
| `pilot_agent/providers/` | Provider adapters for Anthropic, OpenAI, and OpenRouter. |
| `pilot_agent/tools/` | Tool implementations and registry. |
| `pilot_agent/config/` | Config cascade and credentials resolution. |
| `pilot_agent/backends/` | Local and Docker command execution. |

Session history is stored in canonical dataclasses from
`pilot_agent/agent/types.py`. Provider-specific message conversion happens at
the API boundary.
