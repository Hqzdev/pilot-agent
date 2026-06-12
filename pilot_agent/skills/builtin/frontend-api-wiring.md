---
name: frontend-api-wiring
description: Wire Next.js app-router forms, reads, loading states, and errors.
triggers: [nextjs, api, fetch, forms]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use when a Next.js screen needs to read data, submit forms, or show backend
errors to users.

## Steps
1. Use server components for reads when the data is needed at page load.
2. Use server actions for app-local mutations:
   - validate input with a schema or explicit checks
   - return field/global errors
   - call `revalidatePath` or redirect after success
3. Use route handlers for webhooks, public API endpoints, or clients outside
   the Next.js app.
4. Keep client components small. Use `'use client'` only for browser state,
   optimistic UI, or event handlers that cannot be server actions.
5. Show loading states with `loading.tsx` or pending state from `useFormStatus`.
6. Show failures in the UI. Do not only `console.error`.
7. Keep secrets server-side. Never put private tokens in `NEXT_PUBLIC_*`.

## Known pitfalls
- CORS is usually irrelevant when frontend and API live in the same Next.js
  app. Do not add CORS middleware to fix a same-origin bug.
- `'use client'` spreads quickly when server-only imports leak into components.
  Split the interactive leaf instead.
- Server actions need serializable inputs/outputs. Do not return raw database
  clients, Dates without formatting, or Error objects.
- Missing loading/error UI makes a working MVP feel broken.

## Verified commands
- `npm run lint`
- `npm run build`
- `rg -n "NEXT_PUBLIC_.*(KEY|SECRET|TOKEN)" src || true`
