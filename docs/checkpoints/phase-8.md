# Phase 8 checkpoint

## Delivered

- Motion plan domain contract in `backend/app/domain/motion_plan.py`, including discriminated actions, style, warnings, synchronization, contacts, and `MotionPlanPatch`.
- Scene-bound plan validation in `backend/app/domain/motion_plan_validation.py`.
- Prompted planner and correction workflows in `backend/app/application/motion/planner.py`.
- Deterministic plan compile job in `backend/app/application/motion/compile.py`.
- Motion plan API routes in `backend/app/api/routes/motion_plans.py`.
- Frontend Motion workspace for prompt submission, plan cards, warnings, JSON view, duration edits, compile approval, correction preview, apply, and undo in `frontend/src/pages/MotionPage.tsx`.
- Model-independent fixture plan path for repeatable local demos and tests.

## Acceptance Criteria Evidence

- "Walk to the chair, sit, and wave" creates the expected graph and clip:
  `backend/tests/domain/test_plan_compiler_phase9.py::test_walk_sit_wave_plan_compiles_expected_graph_and_clip`.
- Unknown target names reject rather than fabricate objects:
  `backend/tests/domain/test_motion_plan_phase8.py::test_validate_rejects_unknown_references_instead_of_fabricating` and
  `backend/tests/test_motion_plans.py::test_unknown_target_is_rejected_not_fabricated`.
- Malformed plans repair once and fail cleanly if still invalid:
  `backend/tests/test_motion_plans.py::test_malformed_plan_repaired_once_then_fails_cleanly`.
- Plan inspection and edit before compile:
  `frontend/src/pages/MotionPage.tsx` action cards plus
  `backend/tests/test_motion_plans.py::test_compile_links_clip_to_plan_and_recompiles_stably`.
- Generated clips are editable without contacting Ollama:
  `backend/app/application/motion/compile.py` and
  `backend/tests/test_motion_plans.py::test_compile_links_clip_to_plan_and_recompiles_stably`.
- Scoped correction changes only the intended action/range:
  `backend/tests/domain/test_motion_plan_phase8.py::test_apply_patch_changes_only_the_targeted_action` and
  `backend/tests/test_motion_plans.py::test_correction_patch_preview_apply_and_undo`.

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

## Demo Steps

1. Open **Motion** with a project containing a one-actor scene and a chair with a `sit` affordance.
2. Enter "Walk to the chair, sit, and wave" or enable **Use fixture plan**.
3. Generate the plan.
4. Inspect action cards, warnings, synchronization text, and the advanced JSON view.
5. Edit an action duration, save the plan, and press **Approve and compile**.
6. Enter a correction such as "Keep her left foot planted and make the wave smaller", preview the patch diff, apply it, and undo it if needed.

## Architecture Changes

- Ollama remains behind `LLMProvider`; the planner emits `MotionPlanDraft` only.
- The deterministic compiler owns all keyframes and validation metrics.
- Patch preview and patch application are separate operations so the user can review and undo model-suggested changes.
- Compile jobs commit clips atomically and keep recompiled clip ids stable for a source plan.

## Schema Changes And Migrations

- Project schema advanced to `0.5.0`.
- Migration `0.4.0 -> 0.5.0` initializes real `motion_plans`, keeps `generation_records`, and adds clip `source_plan_id` and `engine_version`.
- OpenAPI and generated TypeScript schemas include motion-plan, patch, compile, and validation payloads.
- No database migration was required; project document storage remains file-based and jobs remain in-memory per ADR 0007.

## Known Limitations

- Live model quality depends on the selected local Ollama model, but fixture mode keeps the workflow testable offline.
- The UI edits common parameters only; deep graph editing remains an advanced JSON/debug workflow for now.
- Applying a correction updates the stored plan; recompilation of the affected range is triggered explicitly by **Approve and compile**.

## Deferred Work

- Richer plan graph visualization.
- More editable fields for action-specific parameters.
- Streaming job-event UI instead of polling.

## Risks Discovered

- Planner prompts must stay compact; actor capabilities and action catalogs are intentionally summarized to avoid leaking full project state.
- User edits after a patch can invalidate a plan against a changed scene, so compile revalidates before committing.

## Recommended Next Issue

Begin Phase 9.1: multi-actor scheduling and synchronized contact compilation.
