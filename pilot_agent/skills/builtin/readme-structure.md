---
name: readme-structure
description: Write a product README that shows what was built and how to run it.
triggers: [readme, docs, marketing]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use in Marketing for the user's product README. This is not the Pilot Agent
repository README; adapt it to whatever MVP was built.

## Steps
1. Start with a one-line description: what it is, for whom, and the outcome.
2. Put a screenshot or GIF near the top. If no asset exists, create a TODO line
   that names the exact screen to capture.
3. Explain problem -> solution in three short paragraphs.
4. Add a Quickstart that works from a clean clone:
   - install dependencies
   - set env vars
   - run migrations if any
   - start dev server
5. Add Stack with concrete versions/frameworks.
6. Add Design Decisions only for choices that matter to a maintainer.
7. Add Known Limitations and what is intentionally out of scope.
8. Keep badges minimal and truthful.

## Known pitfalls
- A wall of features without a screenshot reads like vaporware.
- Do not write "WIP" in the header. State the current working scope instead.
- Do not add dead badges for docs, Discord, downloads, or coverage.
- Do not copy Pilot Agent's README structure verbatim when the user's product is
  not a dev tool.

## Verified commands
- `test -f README.md`
- `rg -n "Quickstart|Getting Started|Stack" README.md`
- `rg -n "TODO|WIP" README.md || true`
