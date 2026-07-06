# Local Development

## Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

The compose stack starts PostgreSQL, runs Alembic migrations in the backend container, starts FastAPI on port `8000`, and starts Vite on port `5173`.

## Native Backend

Start PostgreSQL first:

```powershell
docker compose up db
```

Then run:

```powershell
./scripts/dev-backend.ps1
```

Backend URLs:

- API root: http://localhost:8000
- OpenAPI UI: http://localhost:8000/docs
- OpenAPI JSON: http://localhost:8000/api/v1/openapi.json
- Health: http://localhost:8000/api/v1/health

## Native Frontend

```powershell
./scripts/dev-frontend.ps1
```

The frontend runs at http://localhost:5173 and proxies `/api` to the backend.

## VS Code Debugging

The workspace includes shared VS Code configuration for formatting and debugging:

- **Backend: FastAPI** starts PostgreSQL with Docker Compose, runs Alembic migrations,
  then launches Uvicorn on `127.0.0.1:8000`.
- **Frontend: Vite in Chrome** starts Vite on `127.0.0.1:5173` and opens Chrome.
- **Full Stack** starts both debug targets together.

Create `.env` from `.env.example` before launching the backend configuration.
The tasks use workspace-relative paths only, so no user-specific local paths are
stored in the repository.

## Ollama Host Access

Native development uses:

```text
OLLAMA_BASE_URL=http://localhost:11434
```

Docker Compose defaults to:

```text
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

On macOS and Windows Docker Desktop, `host.docker.internal` resolves to the host. On Linux, the compose file maps `host.docker.internal` with `host-gateway`. If Ollama is bound to localhost only and Docker cannot reach it, run the backend natively or configure Ollama to listen on an address reachable from Docker.

Health reachability uses `GET /api/version`; model listing uses `GET /api/tags`;
structured generation uses `POST /api/chat` with a JSON-schema `format`.

## Generate A Character With Ollama

The editor works without Ollama (manual and procedural character building). To use
a live local model for character generation:

1. Install [Ollama](https://ollama.com) and start it. Pull a model that supports
   structured outputs well, for example:

   ```powershell
   ollama pull qwen2.5:7b
   ```

2. Start Postgres, the backend, and the frontend (sections above). Confirm
   `OLLAMA_BASE_URL` points at your Ollama server.
3. Open the app, go to **Settings**, choose the model, and click **Test model**.
   A green "OK" confirms the model honors the structured-output schema.
4. Go to **Characters**, select the model, type a description, and click
   **Generate with AI**. The backend asks Ollama for a `CharacterBlueprint`
   (validated by Pydantic, with one repair retry), then the deterministic builder
   produces the rig and vector art.
5. Review the validated blueprint, warnings, and per-field value provenance
   (model / derived / default). The character and an audit generation record are
   saved together in a new project.

The generation runs as a job: `POST /projects/{id}/characters/generate` returns
`202` with a job resource; poll `GET /jobs/{id}` (or stream `GET /jobs/{id}/events`)
until it reaches a terminal state.

## Checks

Backend:

```powershell
cd backend
python -m pip install -e ".[dev]"
ruff format --check .
ruff check .
mypy app tests
pytest
alembic upgrade head
```

Frontend:

```powershell
cd frontend
npm install
npm run generate:client
npm run lint
npm run typecheck
npm run test
npm run build
npm run e2e
```

Project sample validation (requires the backend package installed, because the
validator imports the domain schemas):

```powershell
python scripts/validate_project_samples.py
```

Release benchmark:

```powershell
python backend/scripts/benchmark_release.py
```

The current baseline is stored in
[`docs/performance/release-baseline.json`](performance/release-baseline.json).
Treat changes as evidence: explain expected regressions or improvements in the
pull request.

## Security And Local Binding

Native backend startup scripts bind Uvicorn to `127.0.0.1`. Docker Compose
publishes container ports to the host for local development; do not treat that
configuration as an authenticated network deployment. If you need a network
listener, add an ADR covering authentication, CORS, CSRF, and user-visible
warnings before enabling it.

Prompt-like API fields are capped at 4,000 characters by request schemas.
Project archive imports are capped at 50 MiB, read from memory with explicit
entry validation and checksum verification; archive entry names are never
trusted as filesystem paths. SVG attachment imports are sanitized before use.

## Shared fixtures and math goldens

The files under `samples/` are generated, not hand-edited. They include the
two-bone and canonical biped rigs, scene fixtures, valid and invalid project
documents, and `samples/fixtures/math-golden.json` — the numerical vectors
that pin the Python (`backend/app/domain/math2d`) and TypeScript
(`frontend/src/engine/math`) kernels to identical behavior, including
bit-identical seeded RNG sequences.

To regenerate after a deliberate schema or generator change:

```powershell
cd backend
python scripts/generate_fixtures.py
```

Then rerun the backend and frontend test suites; golden changes must be
explained in the pull request. In dev mode (`npm run dev`), the frontend
shows a **Dev Fixtures** page that validates the biped demo project in the
browser and lists computed world endpoints.
