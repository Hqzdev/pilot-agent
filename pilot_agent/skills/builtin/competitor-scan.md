---
name: competitor-scan
description: Run a bounded competitor scan and turn it into one differentiation question.
triggers: [discovery, validation, competitors]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use in Discovery when web_search is enabled and the user has an idea but no
clear differentiation. This is not a market research phase; it is a quick
sanity check before planning.

## Steps
1. Run at most three `web_search` calls:
   - `<idea> app`
   - `<idea> open source`
   - `<idea> alternatives`
2. Keep only the three closest analogs. Prefer products with similar users and
   workflows over huge incumbents with one overlapping feature.
3. Summarize each analog in a compact table:
   - name
   - what it does
   - why users choose it
   - obvious gap or angle
4. Ask one question with `ask_user`: "These are the closest competitors. What
   will make your MVP different enough to try?"
5. Write the answer to the Brief section of `.pilot-agent/STATE.md` as
   `Differentiation: ...`.

## Known pitfalls
- Do not turn this into broad market research. Three searches is the hard cap.
- Finding zero competitors is not automatically good news. It can mean the
  search terms are wrong, the need is weak, or the idea is too vague.
- Do not copy competitor features into scope. Use the scan to sharpen the
  first version, not to inflate it.
- Do not ask multiple follow-up questions. One differentiation question is the
  value of this skill.

## Verified commands
- `pilot-agent tools web_search --enable --provider tavily`
- `pilot-agent auth set tavily`
- `pilot-agent config get tools.web_search.provider`
