# Phase 12 checkpoint

## Delivered

- Stabilized the Playwright visual golden by pinning the Chromium viewport to the committed desktop baseline.
- Added API-level prompt text limits for character generation, motion planning, and motion-plan correction requests.
- Added a 50 MiB archive import request limit before archive parsing.
- Regenerated OpenAPI and TypeScript API types after schema limit changes.
- Added release-facing documentation: Ollama setup, first character tutorial, scene/prompt tutorial, handshake tutorial, project format reference, prompt/schema extension guide, contributor guide, license provenance, changelog, issue templates, and PR template.
- Updated README, architecture, dependency-license, development, and performance baseline docs for the current alpha scope.

## Acceptance criteria evidence

- Backend static checks passed.
- Frontend static checks passed.
- Backend unit/integration tests passed.
- Frontend unit tests passed.
- Sample project validation passed, including migration fixtures and invalid sample rejection.
- Frontend production build passed with the known large chunk warning.
- Playwright smoke and visual tests passed.
- Phase 12 benchmark produced project load, motion compile, PNG sequence export, and WebM export measurements.
- Oversized prompt tests prove validation rejects AI inputs over 4,000 characters before any provider call starts.

## Commands run

- `python -m ruff check app tests`
- `python -m mypy app`
- `python -m pytest`
- `python scripts\validate_project_samples.py`
- `python backend\scripts\benchmark_release.py`
- `npm run generate:client`
- `npm run lint`
- `npm run typecheck`
- `npm run test`
- `npm run build`
- `npm run e2e`

## Test results

- Backend full suite: 219 passed.
- Backend targeted prompt/upload-limit suite: 30 passed.
- Frontend unit suite: 100 passed.
- Playwright: 6 passed.
- Sample validation: all valid project/fixture/migration samples accepted; invalid samples rejected as expected.
- Benchmark on this workstation:
  - project load median: 0.448 ms;
  - motion compile median: 9.397 ms;
  - PNG sequence export: 91.721 ms for 15 frames at 320x240;
  - WebM export: 118.533 ms for 8 frames at 160x120.

## Demo steps

1. Start the app with `docker compose up --build` or native scripts.
2. Open `http://localhost:5173`.
3. Use **Characters** to create and save a deterministic procedural character.
4. Use **Rig Editor** to select bones and scrub the manual wave.
5. Use **Scenes** to inspect the semantic snapshot.
6. Use **Motion** to compile a fixture or live-model plan.
7. Follow `docs/tutorial-handshake.md` for the two-character interaction demo.

## Architecture changes

- No boundary changes.
- Prompt-size limits are request-schema constraints in the API layer and are reflected in generated OpenAPI types.
- Playwright viewport pinning affects only test determinism.

## Schema changes and migrations

- API schema changed: LLM request models now include `maxLength` on model names and prompt-like fields.
- Native project schema remains `0.6.0`.
- No database migration was required.

## Known limitations

- Public-alpha acceptance is not fully closed: full accessibility audit, network-mode authentication review, disk-full handling, and final release packaging remain open.
- WebM export still depends on `ffmpeg` on `PATH`.
- Production frontend build still emits the known large chunk warning.

## Deferred work

- Complete keyboard/screen-reader audit with documented findings and fixes.
- Add authenticated network mode or explicitly keep alpha local-only.
- Add disk-full simulation for asset writes and export jobs.
- Add final release tags/checksum artifacts once the repository is ready to publish.

## Risks discovered

- Visual goldens were viewport-dependent until the Playwright viewport was pinned.
- The current Docker Compose backend binds inside the container to `0.0.0.0` for host access; it should not be reused as an authenticated network deployment without an ADR.

## Recommended next issue

Finish the Phase 12 accessibility and security audit: keyboard-only workflow, screen-reader focus order, high-contrast indicators, network-mode authentication decision, and asset disk-full recovery.
