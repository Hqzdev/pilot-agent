# Docker And Sandbox

The installer prefers Docker when the CLI can find `docker` and the daemon is
running. In Docker mode it:

1. Clones or updates the source checkout under `~/.pilot-agent-src`.
2. Builds the Compose image.
3. Writes `~/.local/bin/pilot-agent`.

The wrapper mounts the current project at `/workspace` and stores Pilot Agent home
data in the `pilot-agent-home` named volume at `/home/agent/.pilot-agent`.

Provider env vars remain optional overrides:

```yaml
ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
OPENAI_API_KEY: ${OPENAI_API_KEY:-}
OPENROUTER_API_KEY: ${OPENROUTER_API_KEY:-}
VERCEL_TOKEN: ${VERCEL_TOKEN:-}
```

If no env var is set, `pilot-agent setup` stores secrets in
`~/.pilot-agent/credentials.yaml` inside the named volume.

Common commands:

```bash
pilot-agent sandbox build
pilot-agent backend docker
pilot-agent backend local
pilot-agent doctor
```

If Docker is unavailable, `doctor` reports the exact command to switch to the
local backend or rebuild the sandbox image.
