# Prompt And Schema Extension Guide

## Prompt Registry

Prompt templates live under `backend/app/infrastructure/llm/prompts`. Do not inline durable prompts in service code. Add a new versioned file when behavior changes materially, then update the prompt ID constants and snapshot tests.

## Structured Outputs

Every Ollama structured call sends a Pydantic-generated JSON schema as `format`. The app validates the raw response, attempts one repair through `repair_json.system.v1.md`, and fails cleanly if validation still fails.

Do not:

- accept regex-extracted JSON without validation;
- let a model invent stable IDs;
- let model output execute code, read files, write files, call tools, or choose URLs;
- persist raw model output as domain state.

## Adding Fields

1. Update the backend Pydantic domain model.
2. Add migration logic if the persisted project schema changes.
3. Add valid and invalid fixtures.
4. Regenerate OpenAPI and frontend API types with `npm run generate:client`.
5. Update frontend import validation if the field appears in portable project JSON.
6. Add tests for normal, boundary, and invalid inputs.

Breaking schema changes require migrations and fixture evidence before the plan checklist can be updated.
