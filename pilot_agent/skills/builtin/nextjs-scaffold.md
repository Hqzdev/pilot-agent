---
name: nextjs-scaffold
description: Scaffold a non-interactive Next.js app-router MVP and verify it locally.
triggers: [nextjs, scaffold, setup]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use in Coding when creating a new Next.js app inside an already initialized
Pilot Agent project.

## Steps
1. Run create-next-app with explicit flags so the CLI never blocks:
   `npx create-next-app@latest . --ts --eslint --app --src-dir --tailwind --no-git --import-alias "@/*" --use-npm`
2. Use `--no-git` because the project repository already exists.
3. Keep the app in the project root unless STATE.md explicitly plans a `web/`
   subdirectory.
4. Remove starter content from `src/app/page.tsx`, but keep `layout.tsx` and
   global CSS.
5. Create only the first screen needed by the core flow. Do not build a
   marketing homepage unless the product itself is a landing page.
6. Verify with:
   `npm run lint`
   `npm run build`
   `run_and_check` command `npm run dev -- --hostname 0.0.0.0 --port 3000`
   and `http_probe` `http://127.0.0.1:3000`.

## Known pitfalls
- Interactive create-next-app prompts break non-interactive `bash`; every answer
  must be represented as a flag.
- The sandbox image has npm. Do not switch to pnpm unless the project already
  has pnpm installed and locked.
- A dev server bound to the wrong host can pass locally but fail through a
  container probe. Use `--hostname 0.0.0.0`.
- Do not import server-only modules into client components. If a component uses
  browser state, isolate it behind a small `'use client'` boundary.

## Verified commands
- `npx create-next-app@latest . --ts --eslint --app --src-dir --tailwind --no-git --import-alias "@/*" --use-npm`
- `npm run lint`
- `npm run build`
- `npm run dev -- --hostname 0.0.0.0 --port 3000`
