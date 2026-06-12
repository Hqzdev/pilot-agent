---
name: local-acceptance
description: Hand the local app to the user for manual acceptance before deploy.
triggers: [acceptance, review, check]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use at the end of Coding and in the Acceptance phase before any production
deploy. The goal is to let the user see the working app locally.

## Steps
1. Read the Done section of `.pilot-agent/STATE.md`.
2. Convert each completed item into a user checklist:
   - open X
   - do Y
   - expected result Z
3. Start the app with `run_and_check`. Use the same command that passed during
   Coding.
4. If using the Docker backend and the user needs a browser, tell them the
   exact exposure command:
   `pilot-agent sandbox expose 3000`
5. Ask with `ask_user`: "Please test the checklist. Reply ok, or describe what
   is wrong."
6. If the answer is ok, complete the phase.
7. If the answer is not ok, turn each issue into a concrete TODO candidate and
   ask for confirmation before editing STATE.md.
8. If feedback contradicts the brief or non-goals, say so explicitly and ask
   whether to change scope.

## Known pitfalls
- "Check that everything works" is not an acceptance checklist. Every item must
  have an action and expected result.
- Do not silently fix feedback that changes the agreed MVP. Confirm the scope
  change first.
- Do not deploy before the user has seen the app unless they explicitly skip
  acceptance.
- Keep the app process cleaned up through `run_and_check`; do not leave dev
  servers running.

## Verified commands
- `pilot-agent sandbox expose 3000`
- `curl -fsS http://127.0.0.1:3000 || true`
- `pilot-agent status`
