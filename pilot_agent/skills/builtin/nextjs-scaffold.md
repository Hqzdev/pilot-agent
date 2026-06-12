---
name: nextjs-scaffold
description: Create a Next.js app-router MVP with predictable structure and local checks.
triggers: [nextjs, react, frontend]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use when creating a new React web app for the MVP coding phase.

## Steps
1. Run `npx create-next-app@latest web --ts --eslint --app --src-dir --no-tailwind --import-alias "@/*"`.
2. Put routes under `src/app/`, reusable UI under `src/components/`, and server utilities under `src/lib/`.
3. Keep the first route runnable with `npm run dev -- --hostname 0.0.0.0`.
4. Add a `/health` route if deployment checks need an HTTP probe.

## Known pitfalls
- Do not mix pages router and app router in a new MVP.
- Server-only code must not be imported by client components.
- Containerized runs need `--hostname 0.0.0.0`.

## Verified commands
- `npm run lint`
- `npm run build`
- `npm run dev -- --hostname 0.0.0.0`
