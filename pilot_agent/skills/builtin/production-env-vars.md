---
name: production-env-vars
description: Inventory production environment variables and install them safely.
triggers: [deploy, env, secrets]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use before deployment whenever the code reads `process.env`, `os.environ`, or
settings from `.env`.

## Steps
1. Inventory env usage:
   - Next.js: `rg -n "process\\.env\\." src app lib`
   - Python: `rg -n "os\\.environ|getenv|BaseSettings|Settings" .`
2. Classify each variable:
   - build-time public value
   - runtime secret
   - local-only development value
3. Reject secrets with `NEXT_PUBLIC_` prefixes.
4. Check `.gitignore` includes `.env`, `.env.local`, and provider-specific env
   files that contain secrets.
5. For Vercel, add production values before deploy:
   `printf "%s" "$VALUE" | vercel env add NAME production --token "$VERCEL_TOKEN"`
6. Redeploy after changing env vars.
7. Verify production behavior through the app, not only through dashboard state.

## Known pitfalls
- `NEXT_PUBLIC_*` is bundled into browser JavaScript. Never put private tokens
  there.
- Adding a Vercel env var after deployment requires a redeploy.
- `.env.local` should not be committed. If it appears in git status, stop and
  update `.gitignore` before continuing.
- Missing env vars often look like generic build failures. Search logs for the
  variable name and "undefined".

## Verified commands
- `rg -n "process\\.env\\.|os\\.environ|getenv|BaseSettings" .`
- `git check-ignore .env.local`
- `vercel env ls --token "$VERCEL_TOKEN"`
