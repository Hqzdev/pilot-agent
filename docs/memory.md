# Memory

Memory is plain markdown under `~/.pilot-agent/`:

| File or directory | Purpose |
|---|---|
| `lessons.md` | Lessons extracted from fix cycles. |
| `skills/` | Learned markdown skills. |
| `input_history` | Local prompt history. |

Project state is separate and lives in `.pilot-agent/STATE.md` inside each
project.

Lessons are created when `run_and_check` or related tool observations expose a
reusable failure pattern. Good lessons describe the problem and the concrete
fix. Trivial typos and project-only details should be skipped.

Commands:

```bash
pilot-agent lessons
pilot-agent lessons clear
pilot-agent skills list
pilot-agent skills show <name>
```

Because memory is markdown, users can inspect and edit it with normal tools.
