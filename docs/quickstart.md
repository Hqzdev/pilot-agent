# Quickstart

Install on Linux, macOS, or WSL2:

```bash
curl -fsSL https://raw.githubusercontent.com/Hqzdev/pilot-agent/main/install.sh | bash
```

The installer prints a staged plan before acting, writes command output to a log
under `/tmp`, installs user-space dependencies without sudo, and places
`pilot-agent` in `~/.local/bin`.
When an interactive terminal is available, it immediately starts
`pilot-agent setup` after installation. For install-only automation, pass
`--skip-setup` / `--no-setup` or set `PILOT_AGENT_INSTALL_NO_SETUP=1`.
Use `--native` to force uv tool install, `--docker` to require sandbox mode, and
`--branch <name>` when testing a non-main installer branch.

First project:

```bash
cd path/to/project
pilot-agent init
pilot-agent doctor
pilot-agent run
```

`setup` asks for one thing at a time: provider, API key, model, and optional
Vercel token. You can rerun it anytime with `pilot-agent setup --reconfigure`.
Keys are stored in `~/.pilot-agent/credentials.yaml` with mode `0600`.
You can skip setup in CI by setting env vars such as
`ANTHROPIC_API_KEY`, `PILOT_AGENT_PROVIDER`, and `PILOT_AGENT_MODEL`.

If anything is misconfigured, run:

```bash
pilot-agent doctor
```

Every failed check includes the command that fixes it.
