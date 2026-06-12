---
name: mvp-scoping
description: Cut an idea down to an MVP brief with explicit non-goals and one core flow.
triggers: [discovery, mvp, scope]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use in Discovery when the idea is broad, the user keeps adding features, or
`STATE.md` has no clear Brief / Stack / TODO boundary yet.

## Steps
1. Ask one question at a time with `ask_user`; do not batch a questionnaire.
2. Capture the core problem in one sentence: "User X cannot do Y because Z".
3. Force a single primary user role for v1. If there are buyers, admins, and
   end users, choose one acting role for the first build.
4. Force one platform for v1. Prefer web for shareable MVPs unless the product
   depends on native device capabilities.
5. Ask the non-goals question explicitly: "What is definitely not in this MVP?"
6. Use the forced-ranking fallback when the user says yes to everything:
   "If we can ship only one feature this week, which one proves the product?"
7. Treat auth, payments, admin panels, teams, analytics, and notifications as
   opt-in scope. Include them only when the core flow is impossible without them.
8. Write the brief to `.pilot-agent/STATE.md` in this shape:
   - `## Brief`: problem, target user, core flow, success signal.
   - `## Stack`: chosen stack and why.
   - `## TODO`: only the first vertical slices.
   - `## Known issues`: open decisions and deferred scope.
9. Confirm the brief before Planning. The user should see the trade-offs before
   file structure and schema are generated.

## Known pitfalls
- "MVP in three screens" can silently become twelve screens. Count core screens
  before completing Discovery.
- A user who says "yes, needed" to everything is asking for prioritization help,
  not permission to build everything.
- Do not hide a non-goal by calling it "later" without writing it down. Write
  deferred items explicitly so Coding does not resurrect them.
- Do not start with auth unless unauthenticated use would make the product
  meaningless or unsafe.

## Verified commands
- `pilot-agent init`
- `pilot-agent status`
- `python - <<'PY'\nfrom pathlib import Path\ntext=Path('.pilot-agent/STATE.md').read_text()\nassert '## Brief' in text and '## TODO' in text\nPY`
