# Configuration

User config lives at `~/.pilot-agent/config.yaml`. Project overrides live at
`<project>/.pilot-agent/config.yaml`. Secrets live separately in
`~/.pilot-agent/credentials.yaml`.

## Precedence

Settings are resolved in this order:

1. CLI flags: `--provider`, `--model`, `--config`.
2. Env vars: `PILOT_AGENT_*`.
3. Project config: `.pilot-agent/config.yaml`.
4. User config: `~/.pilot-agent/config.yaml`.
5. Package defaults: `pilot_agent/config/defaults.yaml`.

## Example

```yaml
provider: anthropic
model: claude-sonnet-4-6
base_url: null
summarizer_model: null
budget_ratio: 0.7
max_turns: 200
tool_timeout_s: 120
phases:
  deploy:
    enabled: true
  marketing:
    enabled: true
ui:
  color: auto
  show_token_counter: true
```

Run `pilot-agent config` to see the effective value and source for each key.

## Secrets

Secret resolution is separate from config resolution:

1. Provider/service env var.
2. `~/.pilot-agent/credentials.yaml`.
3. Actionable error with `pilot-agent auth set <service>`.

`credentials.yaml` is written atomically with mode `0600`.

```yaml
anthropic:
  api_key: sk-ant-...
openrouter:
  api_key: sk-or-...
vercel:
  token: ...
```

Use `pilot-agent auth status` to see masked values and whether each secret came
from env or credentials.

## Common Env Vars

| Env | Purpose |
|---|---|
| `PILOT_AGENT_HOME` | Override the user home directory for config, credentials, memory. |
| `PILOT_AGENT_PROVIDER` | Default provider. |
| `PILOT_AGENT_MODEL` | Default model. |
| `PILOT_AGENT_BUDGET_RATIO` | Context budget ratio. |
| `PILOT_AGENT_TOOL_TIMEOUT_S` | Tool timeout in seconds. |
| `ANTHROPIC_API_KEY` | Anthropic credential override. |
| `OPENAI_API_KEY` | OpenAI credential override. |
| `OPENROUTER_API_KEY` | OpenRouter credential override. |
| `VERCEL_TOKEN` | Vercel credential override. |
