# Phase 0 checkpoint

## Delivered

- FastAPI backend skeleton with typed `/api/v1/health`, `/api/v1/settings`, `/api/v1/projects`, and OpenAPI routes.
- SQLModel/PostgreSQL foundation with Alembic migration [`0001_phase_0_foundation.py`](../../backend/alembic/versions/0001_phase_0_foundation.py).
- React/Vite frontend shell built with Fluent UI React v9 in [`AppShell.tsx`](../../frontend/src/components/AppShell.tsx).
- Generated OpenAPI TypeScript types in [`schema.d.ts`](../../frontend/src/api/generated/schema.d.ts), exported from [`export_openapi.py`](../../backend/scripts/export_openapi.py).
- Docker Compose services for PostgreSQL, backend, and frontend in [`docker-compose.yml`](../../docker-compose.yml).
- Local setup docs in [`README.md`](../../README.md) and [`docs/development.md`](../development.md).
- Required ADRs under [`docs/adr`](../adr).
- CI workflow in [`ci.yml`](../../.github/workflows/ci.yml).
- Phase 0 sample project and validator: [`empty-project.rigstory.json`](../../samples/projects/empty-project.rigstory.json), [`validate_project_samples.py`](../../scripts/validate_project_samples.py).

## Acceptance criteria evidence

- **A clean clone starts with documented commands.** Documented in [`README.md`](../../README.md) and [`docs/development.md`](../development.md). Verified `docker compose build backend frontend`, then `FRONTEND_PORT=5174 docker compose up -d backend frontend` returned frontend HTTP `200` and backend health `healthy`.
- **Frontend loads a Fluent UI shell.** [`App.test.tsx`](../../frontend/src/App.test.tsx) and [`smoke.spec.ts`](../../frontend/tests/e2e/smoke.spec.ts) pass against the Projects shell.
- **Backend OpenAPI is reachable.** [`test_openapi.py`](../../backend/tests/test_openapi.py) passes. Live check returned OpenAPI title `RigStory Studio`.
- **PostgreSQL migration completes.** `python -m alembic upgrade head` ran against Compose PostgreSQL and applied revision `0001_phase_0`.
- **Health page distinguishes application healthy from Ollama unavailable.** [`test_health.py`](../../backend/tests/test_health.py) and Playwright smoke test assert core health separately from mocked Ollama `unavailable`.
- **CI passes on an empty feature baseline.** [`ci.yml`](../../.github/workflows/ci.yml) configures backend, frontend, Playwright, project-schema, and dependency-license jobs. Equivalent local checks passed.
- **No animation or AI logic is implemented yet.** Ollama code is limited to `GET /api/version` reachability behind [`LLMProvider`](../../backend/app/infrastructure/llm/provider.py). No character generation, animation, PixiJS runtime, plan generation, or Ollama chat calls were added.

## Commands run

- `python -m pip install -e ".[dev]"`
- `npm install`
- `npm run generate:client`
- `python -m ruff format --check .`
- `python -m ruff check .`
- `python -m mypy app tests scripts`
- `python -m pytest`
- `python scripts/validate_project_samples.py`
- `npm run lint`
- `npm run typecheck`
- `npm run test`
- `npm run build`
- `npm run e2e`
- `npm run license:report`
- `python -m piplicenses --format=json --output-file backend-license-report.json`
- `docker compose up -d db`
- `python -m alembic upgrade head`
- live FastAPI check against `/api/v1/health`, `/api/v1/openapi.json`, and `/api/v1/projects`
- `docker compose build backend frontend`
- `docker run --rm github_repos-backend pytest`
- `FRONTEND_PORT=5174 docker compose up -d backend frontend`
- `docker compose down`

## Test results

- Backend Ruff format: passed.
- Backend Ruff lint: passed.
- Backend mypy strict check: passed.
- Backend pytest: `3 passed`.
- Backend pytest inside container: `3 passed`, with one upstream Starlette `TestClient` deprecation warning.
- Project sample validation: `empty-project.rigstory.json` validated.
- Frontend ESLint: passed.
- Frontend TypeScript check: passed.
- Frontend Vitest: `1 passed`.
- Frontend production build: passed with a Vite chunk-size warning at `500.05 kB`.
- Playwright smoke: `1 passed`.
- License reports generated for backend and frontend.

## Demo steps

1. Start with `docker compose up --build`.
2. Open the frontend at `http://localhost:5173`.
3. View the empty Projects screen.
4. Open Settings and see the Ollama base URL plus connection status.
5. Open Health and compare Application, Database, Assets, and Ollama status rows.
6. Open backend OpenAPI at `http://localhost:8000/docs`.

## Architecture changes

- Introduced backend API, schema, service, infrastructure, and model folders.
- Added an `LLMProvider` health boundary with an Ollama reachability implementation only.
- Added frontend shell, pages, generated API types, and a small typed fetch wrapper.
- Added Docker, native dev scripts, ADRs, CI, and dependency license reporting.

## Schema changes and migrations

- Added PostgreSQL table `app_settings` through Alembic revision `0001_phase_0`.
- Added a Phase 0 sample project envelope with `schema_version: "0.1.0"`.
- No character, scene, animation, LLM payload, or project-domain migration was introduced.

## Known limitations

- Authentication is disabled for Phase 0 local mode; network-mode authentication is deferred.
- The frontend build emits a chunk-size warning from the initial Fluent UI bundle.
- The live machine had Ollama available during the live health check; unavailable behavior is covered by backend and Playwright mocks.
- Remote GitHub Actions were configured but not executed from this local workspace.

## Deferred work

- Phase 1 versioned identifiers, canonical project schemas, and math kernel.
- Real project CRUD and persistence beyond the empty Phase 0 Projects endpoint.
- Ollama model listing, test prompts, structured outputs, and generation jobs.
- PixiJS renderer adapter and all animation/editor workflows.

## Risks discovered

- Docker was installed but not initially running; Docker Desktop had to be started before Compose evidence could be collected.
- Another local app was already bound to port `5173`, so Playwright uses strict port `4173` and Compose verification used `FRONTEND_PORT=5174`.
- Open-ended dependency ranges can resolve newer framework warnings in clean containers; container tests currently pass.

## Recommended next issue

Within Phase 0, push the repository and confirm the configured GitHub Actions workflow is green on the remote runner.
