# CLI Reference

`pilot-agent` is the primary executable. `pilot-agent` is kept as a compatibility
alias.

## Setup And Auth

| Command | Purpose |
|---|---|
| `pilot-agent setup` | Run the four-step first-run wizard. |
| `pilot-agent setup --provider <name>` | Skip provider choice. |
| `pilot-agent setup --reconfigure` | Re-run setup over existing config. |
| `pilot-agent auth set <service>` | Prompt for a secret and store it in `credentials.yaml`. |
| `pilot-agent auth status` | Show configured services, source, masked credential, env name. |
| `pilot-agent auth remove <service>` | Remove a stored secret. |
| `pilot-agent doctor [--json]` | Diagnose environment, config, provider, tools, memory, project. |
| `pilot-agent version` | Print version, commit, Python, platform. |
| `pilot-agent update` | Update docker or native install. |

## Models

| Command | Purpose |
|---|---|
| `pilot-agent model` | Interactive provider/model switch in a TTY. |
| `pilot-agent model <provider>:<model>` | Direct provider/model switch. |
| `pilot-agent model <model>` | Switch model on the current provider. |
| `pilot-agent model --list` | List models for the current provider. |

## Config

| Command | Purpose |
|---|---|
| `pilot-agent config` | Show effective config and source for each key. |
| `pilot-agent config get <key>` | Print one value. |
| `pilot-agent config set <key> <value>` | Validate and write one value with dot notation. |
| `pilot-agent config edit` | Open user config in `$EDITOR`. |
| `pilot-agent config path` | Print the user config path. |

## Work

| Command | Purpose |
|---|---|
| `pilot-agent init [path]` | Initialize `.pilot-agent/STATE.md`. |
| `pilot-agent run` | Start or continue the pipeline. |
| `pilot-agent resume` | Resume from `session.jsonl`. |
| `pilot-agent status` | Show phase, TODO progress, turns, and tokens. |

## Memory And Skills

| Command | Purpose |
|---|---|
| `pilot-agent skills list` | List skills and score metadata. |
| `pilot-agent skills show <name>` | Print a skill body. |
| `pilot-agent skills new` | Edit and save a learned skill. |
| `pilot-agent lessons` | Print `lessons.md`. |
| `pilot-agent lessons clear` | Clear lessons after confirmation. |
| `pilot-agent sessions list` | Show current session summary. |

## Slash Commands

Slash commands are handled in the REPL before sending content to the model:
`/model`, `/skip`, `/compact`, `/usage`, `/state`, `/skills`, `/undo`,
`/help`, and `/quit`.
