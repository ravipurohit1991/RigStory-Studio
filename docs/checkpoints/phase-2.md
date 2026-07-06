# Phase 2 checkpoint

## Delivered

- Manual rig/attachment workspace in [`RigEditorPage.tsx`](../../frontend/src/pages/RigEditorPage.tsx) with setup and animation modes, bone tree selection, numeric inspector edits, reparenting, undo/redo, dirty state, manual save, and debounced autosave after the first saved revision.
- PixiJS adapter updates in [`RigStageAdapter.ts`](../../frontend/src/engine/renderer/RigStageAdapter.ts) to draw primitive attachments under bone world transforms, preserve Y-up conversion in the renderer, and keep rig/attachment state outside PixiJS canonical state.
- Attachment domain/schema support in [`character.py`](../../backend/app/domain/character.py) and [`project.ts`](../../frontend/src/schemas/project.ts): primitive shape specs, pivot, transform, visibility, z-order, SVG/PNG asset references, and asset-required validation.
- Pure frontend attachment helpers in [`attachments.ts`](../../frontend/src/engine/attachments.ts) for primitive generation, immutable attachment updates, PNG data URL checks, and SVG sanitization.
- File-backed local project store in [`project_store.py`](../../backend/app/services/project_store.py) with canonical JSON, revision files, optimistic concurrency, duplicate/delete, failed-save preservation, and restore.
- Project and character REST endpoints in [`projects.py`](../../backend/app/api/routes/projects.py) and [`characters.py`](../../backend/app/api/routes/characters.py).
- OpenAPI types regenerated in [`schema.d.ts`](../../frontend/src/api/generated/schema.d.ts).

## Acceptance criteria evidence

- Small skeleton construction/editing, inherited transforms, cycle prevention, setup locks, and merged drag undo are covered by [`rigEditing.test.ts`](../../frontend/src/engine/rigEditing.test.ts) and [`RigEditorPage.test.tsx`](../../frontend/src/pages/RigEditorPage.test.tsx).
- Attachment validation and sanitization are covered by [`attachments.test.ts`](../../frontend/src/engine/attachments.test.ts) and shared project schema tests.
- Save/reload/duplicate, stale revision rejection, and failed-save preservation are covered by [`test_projects.py`](../../backend/tests/test_projects.py).
- Character CRUD and character-reference integrity are covered by [`test_characters.py`](../../backend/tests/test_characters.py).
- Renderer remains adapter-bound; domain modules do not import PixiJS.

## Commands run

- `python -m pytest`
- `python -m mypy app tests`
- `python -m ruff check app tests`
- `python scripts\validate_project_samples.py`
- `npm run generate:client`
- `npm run lint`
- `npm run typecheck`
- `npm test`
- `npm run build`
- `npm run e2e`

## Test results

- Backend pytest: `92 passed`.
- Backend mypy strict: no issues in 62 source files.
- Backend Ruff: passed.
- Project samples: valid samples loaded and invalid samples rejected as expected.
- Frontend Vitest: `68 passed`.
- Frontend ESLint and TypeScript: passed.
- Frontend build: passed with the existing large-chunk warning.
- Playwright smoke: `2 passed`.

## Demo steps

1. Open the app and choose **Rig Editor**.
2. Select a bone, edit local transform/length in setup mode, and undo/redo.
3. Add a primitive attachment to the selected bone and edit offset, pivot, rotation, scale, visibility, and z-order.
4. Save the project, reload it, duplicate it, and confirm the edited rig/attachments persist.

## Architecture changes

- Phase 2 persistence is file-backed under `asset_store_path/projects`; it is intentionally local and revisioned without introducing future database tables.
- Direct user edits still flow through editor commands; server writes are revisioned project transactions.
- Asset import is validated/sanitized before an attachment can reference the asset ID.

## Schema changes and migrations

- Added optional `primitive` and `pivot` fields to attachment definitions. Existing `0.2.0` project files remain parseable through defaults; no version bump was required.
- No database migration.

## Known limitations

- Imported SVG/PNG assets are sanitized and stored as asset references/manifest entries, but the Pixi adapter currently renders a primitive placeholder for asset attachments rather than the actual raster/vector payload.
- Persistence is a Phase 2 local file store, not the later SQLModel/PostgreSQL persistence model.

## Deferred work

- True SVG/PNG content rendering and content-addressed binary asset serving in the renderer.
- Richer asset archive/export handling in Phase 11.

## Risks discovered

- Browser tests need distinct accessible names because timeline and attachment controls can visibly contain bone IDs.

## Recommended next issue

Within Phase 2 hardening, replace SVG/PNG placeholder rendering with true content rendering; Phase 3 timeline refinements are covered by the Phase 3 checkpoint.
