# Phase 9 checkpoint

## Delivered

- Shared scene timeline scheduling with per-actor lanes and resource-conflict checks in `backend/app/domain/motion_plan.py`.
- Two-actor reference, handedness, pronoun ambiguity, actor-count, and contact-feasibility validation in `backend/app/domain/motion_plan_validation.py`.
- Deterministic multi-actor compiler and handshake primitive in `backend/app/domain/plan_compiler.py`.
- Contact markers, synchronization markers, actor spacing checks, gaze lead/release, and speaking/listening posture markers.
- Fixture and API coverage for "Mira approaches Jon, shakes his right hand, then they both look toward the door."
- Motion workspace action cards show actor ownership and synchronization data.
- Dedicated `frontend/src/pages/Phase9DemoPage.tsx` page that creates/resets the demo scene, calls the real configured Ollama model, and compiles the returned plan.

## Acceptance Criteria Evidence

- Two actors approach without overlap:
  `backend/tests/domain/test_plan_compiler_phase9.py::test_handshake_compiles_contact_sync_and_spacing`.
- Handshake maintains contact within tolerance:
  `backend/tests/domain/test_plan_compiler_phase9.py::test_handshake_compiles_contact_sync_and_spacing`.
- Feet remain planted within tolerance during contact:
  `backend/tests/domain/test_plan_compiler_phase9.py::test_handshake_compiles_contact_sync_and_spacing`.
- Action cards show ownership and synchronization:
  `frontend/src/pages/MotionPage.tsx`.
- Editing one actor's unrelated gesture does not shift the handshake marker:
  `backend/tests/domain/test_plan_compiler_phase9.py::test_editing_unrelated_gesture_keeps_handshake_markers_stable`.
- More than two actors is rejected in the domain schema:
  `backend/tests/domain/test_plan_compiler_phase9.py::test_more_than_two_actors_is_rejected_at_the_scene_schema`.
- Two-actor fixture plans and compiles through the API:
  `backend/tests/test_motion_plans.py::test_handshake_fixture_plans_and_compiles_two_actors`.

## Commands Run

- `.\\.venv\\Scripts\\python.exe -m pytest backend\\tests\\domain\\test_motion_plan_phase8.py backend\\tests\\domain\\test_plan_compiler_phase9.py backend\\tests\\test_motion_plans.py`
- `.\\.venv\\Scripts\\python.exe -m pytest backend\\tests`
- `.\\.venv\\Scripts\\python.exe -m ruff check backend\\app backend\\tests`
- `.\\.venv\\Scripts\\python.exe -m mypy backend\\app`
- `npm run typecheck`
- `npm run test -- --run`
- `npm run lint`
- `npm run build`
- `npm run e2e`
- Live Ollama API demo against `glm-5.2:cloud` through `http://127.0.0.1:8010/api/v1`.

## Test Results

- Focused Phase 8/9 backend: `26 passed`.
- Full backend: `187 passed`.
- Backend Ruff: `All checks passed`.
- Backend mypy: `Success: no issues found in 74 source files`.
- Frontend typecheck: clean.
- Frontend Vitest: `84 passed`.
- Frontend lint: clean.
- Frontend build: successful; Vite reports the existing large chunk warning.
- Playwright: `6 passed`.
- Live Ollama demo: generated a repaired valid plan with actions `approach`, `idle`, `handshake`, `look_at`, `look_at`; compile succeeded with zero target error, zero foot slide, and zero penetration frames.

## Demo Steps

1. Open **Phase 9 Demo**.
2. Press **Create/reset demo**.
3. Press **Generate with real Ollama** using `glm-5.2:cloud`.
4. Verify actor ownership, synchronization, contacts, and generated JSON.
5. Press **Compile handshake**.
6. Inspect zero penetration frames, target error, foot slide, and contact/sync markers in the stored clip.

## Architecture Changes

- The deterministic compiler, not the model, solves approach spacing, contact point selection, hard/follower sides, oscillation, gaze, and release.
- Contact definitions allow one hard reference side and one solved side.
- Scheduling aligns start-together, finish-together, and meet-at-contact constraints while detecting overlapping limb/resource usage.
- Two actors remains a hard product limit under ADR 0006.

## Schema Changes And Migrations

- No additional Phase 9 project-schema migration beyond Phase 8 `0.5.0`.
- Phase 9 uses the Phase 8 motion-plan contact and sync schemas.
- No database migration was required.

## Known Limitations

- Hand-to-object contact is typed and validated, but the richest tested choreography is hand-to-hand handshake.
- Root planning uses deterministic direct/simple-detour paths rather than a navigation mesh.
- Social posture markers are semantic timeline markers without audio or lip-sync.

## Deferred Work

- More contact primitives beyond handshake.
- Richer two-actor plan editing UI.
- Visual golden benchmarks for the handshake scene once Phase 11 sample export/import hardening lands.

## Risks Discovered

- Contact quality depends on actor proportions; validation checks rough feasibility before compile and the report exposes target error.
- Adding more simultaneous contacts will need stricter hard-side selection to avoid over-constraining the deterministic solver.

## Recommended Next Issue

Begin Phase 10.1: weighted mesh foundation for improved bending while keeping rigid characters working unchanged.
