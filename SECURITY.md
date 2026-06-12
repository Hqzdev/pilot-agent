# Security

Pilot Agent runs local commands on behalf of the user, so the v1 security model
is built around sandboxing, explicit tool constraints, and inspectable data
storage.

## Threat Model

- The model may propose a dangerous shell command.
- Tool output may contain secrets or a large volume of data.
- A user may accidentally write an API key to config or history.
- The Docker project mount gives the container access to the workspace.

## Controls

- The recommended install runs agent-owned shell commands inside a Docker
  sandbox under `/workspace`.
- `BashTool` has a blocklist for obviously dangerous commands: `sudo`,
  `rm -rf /`, `mkfs`, and writes to system directories.
- `ToolRegistry` always writes full output to `.pilot-agent/artifacts/` before
  truncation.
- Config stores only environment variable names: `ANTHROPIC_API_KEY`,
  `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, and `VERCEL_TOKEN`.
- `doctor` checks key presence without printing secrets.
- `.pilot-agent/`, `.env`, caches, and virtualenvs are excluded from git.

## Reporting

While the project is early, report vulnerabilities through a GitHub issue
tagged `security`. Do not publish secrets, logs containing keys, or private
workspace files.

## Out of Scope for v1

- A complete sandbox security boundary without Docker.
- Remote execution.
- Multi-user tenancy.
- OAuth portal.
- Network egress policy inside the container.
