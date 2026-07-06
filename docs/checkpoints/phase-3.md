# Phase 3 checkpoint

## Delivered

- Deterministic clip evaluator in [`clip.ts`](../../frontend/src/engine/clip.ts) for rotation, root translation, scale, constraint-weight tracks, stepped/linear/cubic interpolation, shortest-path angle interpolation, loop wrapping, keyframe editing, and applying evaluated poses without mutating setup transforms.
- Native clip import/export and baseline animated SVG export in [`clipExport.ts`](../../frontend/src/engine/clipExport.ts).
- Timeline UI in [`RigEditorPage.tsx`](../../frontend/src/pages/RigEditorPage.tsx): playhead/ruler, play/pause/speed, loop range controls, zoomed horizontal scrolling, track lanes, keyframe select/move/duplicate/delete/copy/paste, numeric keyframe inspector, interpolation presets, scalar curve preview, evaluated value/velocity, autokey, onion-skin toggling, and pose capture in animation mode.
- Sample biped clip remains the manual wave fixture in [`biped-demo.rigstory.json`](../../samples/projects/biped-demo.rigstory.json).

## Acceptance criteria evidence

- Three-pose wave fixture loads and evaluates through the timeline engine.
- Determinism and export/import equivalence are covered by [`clip.test.ts`](../../frontend/src/engine/clip.test.ts) and [`clipExport.test.ts`](../../frontend/src/engine/clipExport.test.ts).
- `359° -> 1°` interpolation is covered by `clip.test.ts` and passes through `0°`.
- Timeline edit controls, loop range controls, zoom/scroll affordances, onion-skin renderer payloads, direct playback pumping, and undo/redo integration are covered by [`RigEditorPage.test.tsx`](../../frontend/src/pages/RigEditorPage.test.tsx).
- Playwright smoke opens the manual rig editor and verifies renderer visibility and bone selection.
- Playwright visual regression covers the manual wave canvas golden in [`smoke.spec.ts`](../../frontend/tests/e2e/smoke.spec.ts).

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
- `npm run e2e -- --update-snapshots`
- `npm run e2e`

## Test results

- Backend pytest: `93 passed`.
- Backend mypy strict and Ruff: passed.
- Frontend Vitest: `73 passed`.
- Frontend ESLint and TypeScript: passed.
- Frontend build: passed with the existing large-chunk warning.
- Playwright smoke and visual regression: `3 passed`.

## Demo steps

1. Open **Rig Editor**.
2. Switch to **Animate**, move the playhead, select a hand/forearm bone, and press **Capture** to add a keyframe.
3. Play the clip, edit key time/value/interpolation, duplicate/copy/paste/delete keyframes, and undo/redo project edits.
4. Export **Clip JSON**, re-import it, and export **SVG**.

## Architecture changes

- Clip evaluation is a pure engine module and does not import React, Fluent UI, PixiJS, or backend code.
- Setup transforms remain immutable; evaluated poses are applied to copied rig data for preview.
- Timeline edits mutate project documents through editor commands.
- Playback advances in a requestAnimationFrame loop that pushes sampled poses directly to the Pixi adapter and throttles React playhead updates for the UI.

## Schema changes and migrations

- Added optional nullable `loop_range` to clip schemas for `[start, end]` playback ranges. Existing documents remain valid with `null`, so no migration was added.
- No database migration.

## Known limitations

- The animated SVG exporter is intentionally skeletal; canvas golden coverage is stronger than SVG output comparison in this phase.

## Deferred work

- Add cross-platform screenshot baselines if CI expands beyond the current Chromium/Windows golden.

## Risks discovered

- The current Vite bundle still emits a large-chunk warning. This predates Phase 3 but the timeline/renderer code makes code-splitting more important before release hardening.

## Recommended next issue

Start Phase 4 procedural character generation; keep an eye on cross-platform screenshot baselines if CI adds more browsers or operating systems.
