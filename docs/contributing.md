# Contributor Guide

Before changing code, read `AGENTS.md`, `specs.md`, `plan.md`, the active phase section, and any ADR touched by the work.

## Local Checks

Backend:

```powershell
cd backend
python -m ruff check app tests
python -m mypy app
python -m pytest
```

Frontend:

```powershell
cd frontend
npm run lint
npm run typecheck
npm run test
npm run build
npm run e2e
```

Samples and benchmark:

```powershell
python scripts/validate_project_samples.py
python backend/scripts/benchmark_release.py
```

## Change Rules

- Work only in the active phase from `plan.md`.
- Keep domain logic independent from FastAPI, React, PixiJS, and Ollama.
- Keep Ollama behind `LLMProvider`.
- Keep PixiJS behind renderer adapters.
- Add migrations for persisted schema breaks.
- Update checkpoints only with evidence from commands, tests, or demo steps.
- Do not copy source from restricted or unlicensed reference repositories.

## Pull Requests

Use `.github/pull_request_template.md`. Include behavior, schema impact, tests run, accessibility/security notes, and known limitations.
