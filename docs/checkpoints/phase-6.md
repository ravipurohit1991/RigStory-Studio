# Phase 6 checkpoint

## Delivered

- Persisted scene schema upgraded to `0.4.0` with explicit object visuals, visibility/locking, collision masks, walkable, and blocked flags.
- Scene CRUD routes:
  - `GET /projects/{project_id}/scenes`
  - `POST /projects/{project_id}/scenes`
  - `GET /scenes/{scene_id}`
  - `PATCH /scenes/{scene_id}`
  - `DELETE /scenes/{scene_id}`
  - `POST /scenes/{scene_id}/validate`
  - `GET /scenes/{scene_id}/snapshot`
- Deterministic scene spatial queries in `backend/app/domain/scene_queries.py`: point, ray, and simple sweep.
- Compact canonical scene snapshots in `backend/app/domain/scene_snapshot.py`.
- Scene validation for duplicate IDs, invalid bounds, invalid/non-convex polygons, missing affordance anchors, actor overlap, blocked starts, and missing walkable ground in authored object scenes.
- Frontend Scene workspace with project/scene selection, object tree, simple spatial preview, validation count, and semantic snapshot preview.

## Acceptance criteria evidence

- Room scene with floor, chair, door, and two actors: `backend/tests/domain/test_scene_phase6.py::room_scene`.
- Maximum actor count remains enforced by schema and existing tests: `backend/tests/domain/test_project.py::test_three_actors_rejected_at_parse_time`.
- Colliders/anchors visible in UI object tree: `frontend/src/pages/SceneEditorPage.tsx`.
- Scene queries with known expected results: `backend/tests/domain/test_scene_phase6.py::test_scene_queries_return_known_results`.
- Snapshot excludes SVG path/texture payload and stays under the budget: `test_scene_snapshot_is_compact_and_byte_stable`.
- Byte-stable snapshot output: `test_scene_snapshot_is_compact_and_byte_stable`.
- API CRUD/snapshot/validation coverage: `backend/tests/test_scenes.py`.
- E2E smoke coverage: `frontend/tests/e2e/smoke.spec.ts` test “opens a semantic scene snapshot and compiles deterministic motion”.

## Commands run

- `python backend/scripts/generate_fixtures.py`
- `python -m pytest backend/tests -q`
- `python -m ruff check backend`
- `python -m mypy backend/app`
- `npm run generate:client`
- `npm run lint`
- `npm run typecheck`
- `npm run test`
- `npm run e2e`

## Test results

- Backend: `161 passed`.
- Backend Ruff: `All checks passed`.
- Backend mypy: `Success: no issues found in 66 source files`.
- Frontend Vitest: `84 passed`.
- Playwright: `6 passed`.

## Demo steps

1. Start the app.
2. Open **Scenes**.
3. Select a project with characters, or create the demo room.
4. Inspect floor/chair/door objects, colliders, anchors, and affordance badges.
5. Refresh the snapshot and verify the canonical semantic JSON has actors, objects, walkable regions, and reachability.

## Architecture changes

- Scene queries and snapshots are pure domain code with no FastAPI, SQLModel, React, or PixiJS imports.
- Scene API routes mutate the existing revisioned project document store.
- The frontend Scene workspace uses API data and does not own canonical project state.

## Schema changes and migrations

- Project schema version advanced from `0.3.0` to `0.4.0`.
- Added migration `0.3.0 -> 0.4.0` to populate default scene visual/editability/query fields.
- Regenerated shared samples and frontend OpenAPI types.

## Known limitations

- The Scene workspace provides a simple spatial preview and object tree, not a full drag-gizmo canvas yet.
- Snapping and transform editing are represented in the data model/API and demo room creation path, but need richer direct manipulation controls.
- Snapshot reachability is a conservative radius estimate from rig arm lengths.

## Deferred work

- Full canvas manipulation handles, snapping controls, and keyboard-numeric transform editing for every scene object.
- Rich blocked-region drawing overlays in the PixiJS renderer.

## Risks discovered

- Older samples used `kind: "floor"` before `walkable`; validation now treats floor/ground as walkable for compatibility.

## Recommended next issue

Begin Phase 8.1: define validated `MotionPlan` action schemas that compile through the deterministic Phase 7 engine.
