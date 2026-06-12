---
name: nextjs-vercel-deploy
description: Deploy a Next.js app to Vercel with token auth, env vars, and build-error recovery.
triggers: [nextjs, vercel, deploy]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use first in the deploy phase for a Next.js MVP targeting Vercel.

## Steps
1. Confirm `VERCEL_TOKEN` is present: `test -n "$VERCEL_TOKEN"`.
2. Link or create the project with `vercel --yes --token "$VERCEL_TOKEN"`.
3. Add env vars with `printf "%s" "$VALUE" | vercel env add NAME production --token "$VERCEL_TOKEN"`.
4. Deploy with `vercel --prod --yes --token "$VERCEL_TOKEN"`.
5. Verify the production URL with `curl -fsSI "$PROD_URL"`.

## Known pitfalls
- Interactive `vercel login` is brittle inside Docker; use `--token`.
- Missing build env vars often appear only during `vercel --prod`.
- If Next.js build fails on TypeScript, reproduce locally with `npm run build` before redeploying.

## Verified commands
- `vercel --prod --yes --token "$VERCEL_TOKEN"`
- `curl -fsSI "$PROD_URL"`
