---
name: nextjs-vercel-deploy
description: Deploy a Next.js app to Vercel non-interactively and verify the production URL.
triggers: [nextjs, vercel, deploy]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use as the first action in the Deploy phase for a Next.js app targeting Vercel.

## Steps
1. Confirm `VERCEL_TOKEN` is available through env or credentials.
2. Run a local production build first:
   `npm run build`
3. Link the project non-interactively when needed:
   `vercel link --yes --token "$VERCEL_TOKEN"`
4. Add required env vars before production deploy:
   `printf "%s" "$VALUE" | vercel env add NAME production --token "$VERCEL_TOKEN"`
5. Deploy:
   `vercel --prod --yes --token "$VERCEL_TOKEN"`
6. Extract the final `https://*.vercel.app` URL from output.
7. Verify with `run_and_check` using an HTTP probe against the production URL.

## Known pitfalls
- Vercel login prompts are hostile to agent sessions. Always use
  `--token "$VERCEL_TOKEN"`.
- Production builds run on Linux. Imports that work on macOS can fail from
  filename casing differences.
- TypeScript errors can appear only in production build if local dev skipped
  `npm run build`.
- Env vars added after a deploy do not affect that deploy. Add them first or
  redeploy.
- Build logs are in Vercel output and dashboard. Read the first failing file,
  not only the final summary.

## Verified commands
- `npm run build`
- `vercel link --yes --token "$VERCEL_TOKEN"`
- `vercel --prod --yes --token "$VERCEL_TOKEN"`
- `curl -fsS https://<deployment>.vercel.app`
