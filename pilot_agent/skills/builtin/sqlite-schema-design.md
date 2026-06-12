---
name: sqlite-schema-design
description: Design small SQLite schemas with normalization, indexes, and migration files.
triggers: [sqlite, database, schema]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use for local-first MVP persistence or a small single-file database.

## Steps
1. Model core entities first; avoid JSON blobs for fields that need filtering.
2. Add `created_at` and `updated_at` where user-visible history matters.
3. Add indexes for foreign keys and common lookup columns.
4. Store migrations as numbered SQL files such as `migrations/001_init.sql`.
5. Verify with `sqlite3 app.db < migrations/001_init.sql`.

## Known pitfalls
- SQLite does not enforce foreign keys unless `PRAGMA foreign_keys = ON`.
- Avoid destructive migrations; create a backup before schema changes.
- Keep text timestamps in UTC ISO-8601 format for portability.

## Verified commands
- `sqlite3 app.db ".schema"`
- `sqlite3 app.db "PRAGMA foreign_key_check;"`
