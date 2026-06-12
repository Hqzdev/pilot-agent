# Contributing

Thanks for contributing to Pilot Agent. The v1 goal is a local CLI/TUI agent
that guides a user from product idea to deployed MVP without web UI, gateways,
or unnecessary platform infrastructure.

## Dev Setup

```bash
./setup-dev.sh
./pilot-agent-dev --help
```

If `uv` is not installed yet:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Checks Before a PR

```bash
scripts/run_tests.sh
```

The script runs ruff, mypy, pytest, compileall, and the CLI smoke check. CI uses
the same entry point so local and GitHub checks match.

## PR Process

1. Keep PRs small and focused.
2. Update tests with behavior changes.
3. Update docs/examples when CLI, config, or Docker UX changes.
4. Do not add secrets to config, tests, or fixtures.
5. Make sure `scripts/run_tests.sh` is green.

## Conventional Commits

Use this format:

- `chore(repo): scaffold repository structure`
- `feat(cli): add setup wizard`
- `fix(tools): enforce artifact persistence`
- `test(providers): cover malformed tool arguments`
- `docs(readme): update Docker install flow`

Commit messages must be short and specific. Do not write `AI generated`,
`admin did this`, or multiple unrelated topics in one commit.
