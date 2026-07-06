# Phase 11 checkpoint

## Delivered

- Added portable project archives with manifest, canonical `project.json`,
  content-addressed assets, checksums, safe zip entry validation, conflict
  handling, and import migration reporting.
- Added in-place project upgrade backup before schema migration.
- Added a native TypeScript runtime package independent of editor UI, with
  versioned API, document loading, clip resolution, playback controls, looping,
  seeking, rendering, and event callbacks.
- Added backend clip media export jobs for PNG sequence, animated SVG, and WebM,
  including frame rate, dimensions, background/transparency settings, progress,
  cancellation cleanup, checksums, and download URLs.
- Added third-party format adapter protocol and empty registry, with ADR 0008
  documenting licensing research requirements and no exact Spine parity promise.

## Acceptance criteria evidence

- Exported archives round-trip through `/api/v1/projects/{project_id}/export`
  and `/api/v1/projects/import`, including clean-workspace import and conflict
  reassignment.
- Archive checksums reject tampered `project.json` and unlisted asset entries.
- Older archive fixture `walker-project-0.3.0.rigstory.json` migrates to the
  current schema and reports applied steps.
- `FileProjectStore.get_project()` backs up legacy current documents before
  writing the upgraded revision.
- Runtime package loads `clip_wave`, resolves scene and character data, renders
  frames, plays, pauses, seeks, loops, and dispatches clip events in unit tests.
- PNG sequence and WebM exports produce downloadable artifacts with frame count,
  duration, frame rate, dimensions, and media type metadata.
- Cancellation of media export removes temporary artifacts.

## Commands run

- `python -m ruff check app tests`
- `python -m mypy app`
- `python -m pytest`
- `python scripts\validate_project_samples.py`
- `npm run generate:client`
- `npm run lint`
- `npm run typecheck`
- `npm run test`
- `npm run build`
- `npm run e2e`

## Test results

- Backend: 216 passed.
- Frontend unit: 97 passed.
- Playwright: 6 passed.
- Sample validation: all project and migration samples accepted; invalid
  samples rejected as expected.
- Frontend production build passed with the existing large chunk warning.

## Demo steps

1. Create or open the two-character demo project.
2. Export it through `GET /api/v1/projects/{project_id}/export`.
3. Import the archive through `POST /api/v1/projects/import`; on conflict, the
   imported project receives a new ID.
4. Start `POST /api/v1/clips/{clip_id}/export` with `png_sequence`, `webm`, or
   `animated_svg`.
5. Poll `/api/v1/jobs/{job_id}` until success and download the returned
   `download_url`.
6. Use `createPlayer()` from `frontend/src/runtime` to load the imported
   project document and play the exported alpha demo clip outside the editor UI.

## Architecture changes

- Project archive code stays in `app.services.project_archive`, outside the
  domain model.
- Media export is job-based and writes artifacts to `data/exports` only after a
  successful temporary render/package step.
- Native runtime remains frontend engine code with no React, Fluent UI, or
  PixiJS imports.
- Third-party adapters are isolated in `app.application.exports.adapters`.

## Schema changes and migrations

- No project schema version change was required; current persisted project
  schema remains `0.6.0`.
- OpenAPI and generated TypeScript API types were regenerated for the clip
  export endpoint and media export schemas.
- No database migration was required.

## Known limitations

- Backend WebM export requires `ffmpeg` on `PATH`; missing encoders fail the job
  with a classified `export_encoder_missing` error.
- Animated SVG export embeds rendered PNG frames; it is portable and animated,
  but not an editable vector-rig interchange format.
- Media export is available through API/client helpers, not yet as a polished
  frontend export panel.

## Deferred work

- Export UI for choosing format, frame rate, size, and transparency.
- Larger clean-profile import demo automation.
- Release packaging of the runtime as a separate npm artifact.

## Risks discovered

- The frontend production bundle still emits the known large chunk warning.
- WebM encoder availability must be documented for clean installs.

## Recommended next issue

Begin Phase 12 with performance hardening: add a reproducible benchmark command
covering project load, runtime render, PNG export, and WebM export on the
alpha two-character scene.
