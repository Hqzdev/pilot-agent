---
name: readme-structure
description: Structure a dev-tool README with quickstart, demo, architecture, and decisions.
triggers: [readme, docs, marketing]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use when writing or refreshing README.md for a developer tool or CLI.

## Steps
1. Start with one sentence explaining what the tool does.
2. Add quickstart for Docker first, then native install.
3. Include a demo GIF or terminal transcript when available.
4. Document config, environment variables, data directories, and security model.
5. Add design decisions and known limitations.

## Known pitfalls
- Do not bury install instructions below architecture notes.
- Avoid secret examples with real-looking keys.
- Keep troubleshooting close to commands users actually run.

## Verified commands
- `devagent --help`
- `docker compose run --rm devagent init`
