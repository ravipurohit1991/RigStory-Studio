# ADR 0007: Generation Records in the Project Document, Jobs In-Memory

Status: Accepted

## Context

Phase 5 introduces AI character generation. Two pieces of state need a home:
the audit record of a generation (original request, model, prompt versions,
options, raw and validated responses, repair attempts, timings, validation
outcome — FR-CHAR-005, specs §21.7) and the transient job that runs the work
(specs §23.6, plan §5.4). The `specs.md` §24 data model lists `jobs` and
`generation_records` database tables, but the project store chosen in Phase 2 is
file-based (`FileProjectStore`), and the `ProjectDocument` already reserved an
empty `generation_records` field "for Phase 5". The database currently holds only
`app_settings`.

## Decision

- **Generation records are persisted inside the project document.** The project
  schema is migrated `0.2.0 → 0.3.0`, replacing the reserved empty
  `generation_records` placeholder with a real `GenerationRecord` item schema. A
  generated character and its record are appended in a single revision
  (`FileProjectStore.commit_generated_character`), so they commit together or not
  at all. Only successful/repaired generations write a record; a failed
  generation leaves the project untouched and its diagnostics live on the job.
- **Jobs run in an in-memory async runner** (`app/application/jobs.py`) with the
  full state machine (queued/running/succeeded/failed/cancelled), progress
  events, SSE streaming, and cooperative cancellation. Jobs are process-local and
  are not persisted to the database.

## Consequences

- Records travel with the project and its portable export (Phase 11) with no
  extra storage mechanism, and prompt content stays under user control rather
  than in ordinary logs.
- No new database migration is required in Phase 5; `alembic upgrade head` is
  unchanged.
- Job history does not survive a backend restart. This is acceptable for a
  single-user local-first alpha. If durable multi-session jobs or a
  database-backed `generation_records` table become necessary, they can be added
  behind the existing `JobRunner` interface and the record model without changing
  callers.
