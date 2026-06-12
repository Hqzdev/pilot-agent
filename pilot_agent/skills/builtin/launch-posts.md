---
name: launch-posts
description: Draft launch posts for r/SideProject, Show HN, and Product Hunt.
triggers: [reddit, launch, marketing, post]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use in Marketing after the MVP is working and README/screenshots exist.

## Steps
1. For r/SideProject, draft:
   - what was built
   - why it exists
   - stack
   - demo link or screenshot/GIF
   - one specific feedback ask
2. Keep the tone non-salesy. Prefer "I built..." over "Introducing the best...".
3. For Show HN, use title format:
   `Show HN: <Product> - <plain outcome>`
4. Draft a first comment for Show HN with build context, trade-offs, and what
   feedback is useful.
5. For Product Hunt, draft a teaser with tagline, maker comment, and first
   three gallery asset ideas.
6. Write outputs to `marketing/launch-posts.md`.

## Known pitfalls
- A post without a screenshot or GIF is usually ignored.
- Cross-posting the same text into multiple subreddits can get removed or
  banned. Adapt each post.
- The first few hours matter. The maker should reply to comments quickly.
- Do not overclaim. Say what works today and what is intentionally missing.

## Verified commands
- `mkdir -p marketing`
- `test -f marketing/launch-posts.md`
- `rg -n "Show HN:|r/SideProject|Product Hunt" marketing/launch-posts.md`
