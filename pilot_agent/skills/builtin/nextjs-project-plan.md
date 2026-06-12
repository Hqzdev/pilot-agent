---
name: nextjs-project-plan
description: Plan a Next.js app-router MVP with vertical slices and minimal structure.
triggers: [nextjs, planning, structure]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use in Planning for a Next.js full-stack MVP before writing the TODO list.
Prefer this over a generic file-tree plan when the stack includes Next.js.

## Steps
1. Use app router as the default. Plan `src/app` for routes, `src/components`
   for reusable UI, `src/lib` for server utilities, and `src/server` only when
   the backend grows beyond small route handlers/actions.
2. Choose server actions for form mutations that are naturally called from the
   app UI. Choose route handlers when the endpoint must be called by external
   clients, webhooks, or tests.
3. Slice TODO vertically. A useful TODO is "create item end to end: schema,
   form, validation, persistence, list refresh", not "build all database code".
4. Put the core value slice before auth, settings, analytics, admin screens, or
   design polish unless the brief says those are core.
5. Write the plan into `.pilot-agent/STATE.md`:
   - Files: concrete paths, not broad folders only.
   - Schema: entities, indexes, and ownership.
   - TODO: ordered vertical slices with verification command per slice.
6. Ask the user to confirm the plan before Coding.

## Known pitfalls
- Do not add Turborepo, workspaces, or package boundaries for a one-app MVP.
- Do not make "auth" the first slice unless the product has no useful anonymous
  path and all data is private from the start.
- Avoid a huge `components/ui` dump. Create only components needed by current
  slices.
- Do not use route handlers for every mutation by reflex; server actions reduce
  boilerplate for app-local forms.

## Verified commands
- `npm run lint`
- `npm run build`
- `find src/app src/components src/lib -maxdepth 2 -type f | sort`
