# Phase 5 checkpoint

## Delivered

- Provider-neutral LLM interface and an HTTP Ollama provider behind it:
  - `backend/app/infrastructure/llm/provider.py` (`LLMProvider` protocol, `ModelInfo`, `ChatMessage`, `GenerationOptions`, `ChatResult`, typed `ProviderError`/`ProviderTimeoutError`).
  - `backend/app/infrastructure/llm/ollama.py` (`OllamaProvider`: `/api/version` health, `/api/tags` model listing, `/api/chat` with a JSON-schema `format` and options; injectable transport for tests).
  - `backend/app/infrastructure/llm/mock.py` (`ScriptedLLMProvider` for tests and model-independent operation).
- Strict `CharacterBlueprint` schema, safety validation, and a deterministic blueprint→builder mapping with per-field provenance:
  - `backend/app/domain/blueprint.py`.
- Versioned prompt registry with field-preservation, bias/stereotype, and child/teen safeguards:
  - `backend/app/infrastructure/llm/prompt_registry.py` and `backend/app/infrastructure/llm/prompts/*.md`.
- Generation record schema persisted in the project document (schema bumped `0.2.0` → `0.3.0` with a migration):
  - `backend/app/domain/generation.py`, `backend/app/domain/project.py`, `backend/app/domain/migrations.py`, `backend/app/domain/versioning.py`.
- Character generation use case with one repair retry, retry classification, and atomic commit:
  - `backend/app/application/characters/generate.py`, `backend/app/services/project_store.py` (`commit_generated_character`).
- In-memory async job orchestration (states, progress events, cancellation, SSE):
  - `backend/app/application/jobs.py`.
- API routes: `GET /ollama/models`, `POST /ollama/test`, `POST /projects/{id}/characters/generate` (202 + job), `GET /jobs/{id}`, `POST /jobs/{id}/cancel`, `GET /jobs/{id}/events`.
- Frontend: Ollama model selector + test in Settings; an AI generation panel in the Character Builder (prompt, model, generate, progress, blueprint preview, warnings, value provenance, compare-with-previous), preserving deterministic region regeneration:
  - `frontend/src/pages/SettingsPage.tsx`, `frontend/src/pages/CharacterBuilderPage.tsx`, `frontend/src/api/client.ts`, `frontend/src/schemas/project.ts` (0.3.0 + generation-record schema).

## Acceptance Criteria Evidence

- A mocked invalid response triggers repair and succeeds: `tests/application/test_generation.py::test_invalid_then_valid_triggers_repair`, API `tests/test_character_generation.py::test_generate_repairs_invalid_first_response`.
- A still-invalid response fails without corrupting project state: `test_still_invalid_fails_without_corrupting_project`, `test_generate_failure_leaves_project_unchanged`.
- A live local model can generate a valid blueprint through documented steps: `docs/development.md` → "Generate a character with Ollama".
- The deterministic generator, not the LLM, creates the SVG and rig: the service maps the blueprint to a `CharacterBuilderRequest` and calls `build_procedural_character`; asserted by `test_generation_success_commits_character_and_record` (25-bone canonical rig, attachments present).
- The user can inspect which values came from the model vs normalized: `FieldProvenance` in the result and the builder clamp diagnostics; shown in the Character Builder AI panel; asserted in `test_blueprint.py` and the UI test.
- Generation records include model, prompt version, options, timings, and validation outcome: `test_generation_record_captures_audit_fields`.
- Timeout vs invalid classification: `test_timeout_is_retryable`, `test_generate_timeout_is_retryable`.

## Commands Run

- `backend`: `python -m ruff format --check .`
- `backend`: `python -m ruff check .`
- `backend`: `python -m mypy app tests`
- `backend`: `python -m pytest`
- `backend`: `python scripts/generate_fixtures.py`
- `repo`: `python scripts/validate_project_samples.py`
- `frontend`: `npm run generate:client`
- `frontend`: `npm run lint`
- `frontend`: `npm run typecheck`
- `frontend`: `npm test`
- `frontend`: `npm run build`
- `frontend`: `npm run e2e`

## Test Results

- Backend: 153 pytest tests passed (was 100); Ruff format + lint clean; mypy strict clean on `app` and `tests`.
- Frontend: 84 Vitest tests passed (was 81); ESLint clean; typecheck clean; production build succeeded.
- E2E: 5 Playwright tests passed, including a new mocked-Ollama generation flow and the existing manual-wave visual golden.
- Samples: all shared samples validate, including the new `generated-character.rigstory.json` and the `0.1.0 → 0.2.0 → 0.3.0` migration chain.
- `alembic upgrade head` is unchanged (no new DB migration; requires Postgres, exercised in CI).

## Demo Steps

1. Start Postgres, the backend, and the frontend (see `docs/development.md`), and ensure Ollama is running with at least one model pulled.
2. Open **Settings**, pick a local model, and click **Test model** to confirm structured-output support.
3. Open **Characters**, choose a model, type a description (e.g. "a calm older shopkeeper in a green apron"), and click **Generate with AI**.
4. Inspect the validated blueprint summary, warnings, and value provenance (model / derived / default).
5. The generated character opens in the deterministic preview; open **Rig Editor** to pose it. The character and its generation record are saved in a new project.

## Architecture Changes

- Added an `app/application` layer for use cases (character generation) and job orchestration, keeping the domain framework-free.
- The Ollama Python package is not imported; the provider is the only module that knows the wire format.
- Jobs are process-local (in-memory) with a clean interface; a DB-backed runner can replace it without changing callers.
- New ADR: `docs/adr/0007-generation-records-in-project-document.md`.

## Schema Changes and Migrations

- Project document schema `0.2.0` → `0.3.0`: the reserved empty `generation_records` placeholder became a real `GenerationRecord` item schema.
- Migration `0.2.0 → 0.3.0` registered (`app/domain/migrations.py`) and covered by `tests/domain/test_migrations.py`; the frontend import layer (`schemas/project.ts`) and all shared samples were updated.
- No database migration: generation records live in the project document, and jobs are in-memory.

## Known Limitations

- Jobs are not persisted across a backend restart.
- The frontend AI panel creates a new project per generation (mirrors the existing Save flow) rather than generating into a currently open project.
- The blueprint carries richer descriptive intent (face detail, silhouettes, outline weight) than the Phase 4 builder currently consumes; those fields are retained in the record for future phases.

## Deferred Work

- Database-backed `jobs` and `generation_records` tables (specs §24) if multi-session durability is needed.
- Regional AI regeneration (blueprint-section requests) is Phase 10; Phase 5 keeps deterministic region regeneration.

## Risks Discovered

- The frontend and backend deterministic builders must stay in parity; the AI preview relies on the TS builder reproducing the backend character from the returned normalized request.
- `ruff format --check .` and `mypy tests` (both CI gates) were not run by earlier phases; a few pre-existing files were reformatted (formatting only, no logic change) to make the format gate green.

## Recommended Next Issue

Begin Phase 6.1: scene CRUD and actor instances, so generated characters can be placed into a scene ahead of the Phase 7 motion engine.
