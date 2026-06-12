---
name: bugfix-intake
description: Reproduce a bug before fixing it, apply a minimal change, and verify the same path.
triggers: [bug, fix, debug]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use when the user returns with a production issue, broken local behavior, failed
check, or "fix this" request.

## Steps
1. Ask for the smallest missing reproduction detail: steps, URL, command,
   screenshot text, expected behavior, or actual error.
2. Reproduce before editing:
   - run the failing command
   - run `run_and_check`
   - or add a focused failing test
3. Record the reproduction in `.pilot-agent/STATE.md` Known issues or TODO.
4. Make the smallest change that targets the reproduced failure.
5. Verify with the exact same reproduction path.
6. Run the existing nearby checks so the fix does not break adjacent behavior.
7. Update Done with the fix and the verification command.

## Known pitfalls
- Fixing from a verbal description without reproduction usually creates a
  second bug.
- Do not refactor unrelated code in a bugfix. Keep the diff narrow.
- A screenshot of an error is not enough if the command or route is missing.
  Ask for the missing reproduction input.
- If the bug contradicts the original brief, ask whether the product behavior
  should change before coding.

## Verified commands
- `pilot-agent status`
- `rg -n "Known issues|TODO|Done" .pilot-agent/STATE.md`
- `run_and_check` with the same command or URL that reproduced the failure
