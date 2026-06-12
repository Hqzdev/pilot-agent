# Skills

Skills are markdown procedures that the model can load only when needed.
Prompts receive the skill index; full bodies are disclosed through the
`load_skill` tool.

Builtin skills live in `pilot_agent/skills/builtin/`. Learned skills live under
`~/.pilot-agent/skills/`.

Each skill starts with YAML frontmatter:

```yaml
---
name: nextjs-vercel-deploy
description: Deploy a Next.js app to Vercel.
triggers: [deploy, nextjs]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
```

Commands:

```bash
pilot-agent skills list
pilot-agent skills show <name>
pilot-agent skills new
```

Learned skills are scored after use. A learned skill with repeated failures can
be marked deprecated and removed from future prompt indexes.
