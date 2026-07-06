# Phase 7 checkpoint

## Delivered

- Deterministic programmatic motion engine in `backend/app/domain/motion.py`.
- Constraint contract models for joint limits, look-at, position target, orientation target, weights, and time ranges.
- Analytic two-bone IK with bend direction, reach clamping, softness, deterministic repeatability, and target-error metrics.
- Programmatic action primitives for stand/idle, shift weight, locomote, turn, look-at, reach, point, wave, grasp/release, sit/rise, crouch/kneel, lean, approach, and retreat.
- Root-path traversal with simple blocked-collider detours, gait swing keys, seated pose keys, and editable `AnimationClip` output.
- Validation report with joint, foot-slide, target-error, penetration, curve-reduction, and action-linked warning fields.
- Demo compile API: `POST /motion/demo/compile`.
- Frontend Motion workspace that compiles the walk/turn/sit/wave demo without Ollama.

## Acceptance criteria evidence

- Walk five units and stop: `backend/tests/domain/test_motion_phase7.py::test_compile_walk_turn_sit_wave_sequence_is_deterministic`.
- Turn toward a target without leg inversion: same test asserts editable bone rotation/root tracks and zero joint-limit metric.
- Reach reachable target with preferred elbow bend: `test_two_bone_ik_reaches_and_clamps_deterministically`.
- Clamp unreachable target: `test_two_bone_ik_reaches_and_clamps_deterministically` and `test_compile_reach_reports_unreachable_target`.
- Sit on configured chair anchor and wave while seated: `test_compile_walk_turn_sit_wave_sequence_is_deterministic`.
- Walk around simple obstacle: same test asserts `PATH_DETOUR`.
- Maintain planted-foot slide tolerance: report metric asserted as `0.0`.
- No joint-limit violations in benchmark sequence: report metric asserted as `0.0`.
- Identical regeneration: same compile input equality asserted in `test_compile_walk_turn_sit_wave_sequence_is_deterministic`.
- API coverage: `backend/tests/test_motion.py`.
- E2E smoke coverage: `frontend/tests/e2e/smoke.spec.ts`.

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

1. Open **Motion**.
2. Use a project containing a scene with a chair anchor.
3. Press **Compile**.
4. Inspect the report status, track count, and target-error metric.
5. The returned clip is ordinary editable track/keyframe data.

## Architecture changes

- Motion compilation is pure backend domain logic and does not call Ollama.
- The compile endpoint is a developer workflow that returns a clip/report without mutating project state.
- Generated motion remains native `AnimationClip` data consumed by existing timeline infrastructure.

## Schema changes and migrations

- No persisted clip schema migration was needed.
- OpenAPI gained motion action, compile request, compile result, and validation report schemas.

## Known limitations

- The path planner uses a deterministic simple detour rather than a full navigation mesh.
- The FABRIK/CCD fallback is represented by deterministic clamping in this phase; complex multi-joint chains remain future work.
- Naturalness controls are intentionally lightweight and algorithmic.
- The frontend Motion page is a developer compile panel rather than the Phase 8 plan-preview workflow.

## Deferred work

- Rich debug visualization of constraints and per-sample validation overlays.
- More advanced collision recompile strategies when no simple detour exists.
- Broader golden motion benchmark fixtures for every primitive.

## Risks discovered

- Keeping the engine deterministic is straightforward for scalar/keyframe output, but richer obstacle avoidance will need careful benchmark fixtures to avoid nondeterministic route choices.

## Recommended next issue

Begin Phase 8.1: `MotionPlan` schemas and validated action graph compilation through this deterministic engine.
