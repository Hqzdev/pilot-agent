---
name: sqlite-schema-design
description: Design a pragmatic SQLite schema with constraints, indexes, and file migrations.
triggers: [sqlite, database, schema]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use in Planning or Coding when the MVP stores relational data in SQLite.
Use it before writing migrations or persistence code.

## Steps
1. Start from the real queries in STATE.md. Add indexes for those queries, not
   for every foreign key by habit.
2. Use lowercase snake_case table and column names. Prefer singular table names
   only if the existing project already does.
3. Enable foreign keys on every connection: `PRAGMA foreign_keys = ON;`.
4. Use `STRICT` tables when SQLite version supports them. They catch accidental
   text/integer drift early.
5. Use `created_at` and `updated_at` as ISO-8601 text or integer epoch; be
   consistent across all tables.
6. Store migrations as numbered SQL files, for example
   `migrations/001_initial.sql`.
7. Add a `schema_version` table:
   `CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);`
8. Make the runner idempotent: apply only migrations whose version is not
   already recorded.
9. For web apps, enable WAL mode once per database:
   `PRAGMA journal_mode = WAL;`.

## Known pitfalls
- SQLite foreign keys are off by default. If deletes or inserts behave oddly,
  verify `PRAGMA foreign_keys;` returns `1`.
- Do not denormalize before seeing repeated joins or read bottlenecks. For MVPs,
  constraints are usually more valuable than premature denormalization.
- Case-sensitive filenames matter in Linux deploy builders. Keep migration file
  imports lowercase and exact.
- Do not hide schema state in Python code only; SQL files are easier for the
  agent and user to inspect.

## Verified commands
- `sqlite3 app.db 'PRAGMA foreign_keys = ON; PRAGMA foreign_keys;'`
- `sqlite3 app.db 'PRAGMA journal_mode = WAL;'`
- `sqlite3 app.db '.schema'`
