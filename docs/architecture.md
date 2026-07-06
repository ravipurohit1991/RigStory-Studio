# RigStory Studio Architecture

RigStory Studio is a local-first full-stack app with strict boundaries between domain state, deterministic animation logic, renderer adapters, and AI planning.

## Runtime Shape

- **Backend presentation:** FastAPI exposes typed `/api/v1` routes and OpenAPI.
- **Backend domain:** Pydantic domain models, project migrations, geometry, rig, scene, clip, mesh, motion-plan, and compiler logic remain free of FastAPI, SQLModel, React, PixiJS, and Ollama imports.
- **Backend application:** Character generation, motion planning, compilation, exports, and jobs orchestrate domain logic and persistence.
- **Backend infrastructure:** Ollama, prompts, image-provider contracts, database, asset storage, archives, and media export live behind adapters.
- **LLM boundary:** Ollama is hidden behind `LLMProvider`. Model output is treated as untrusted JSON, validated with Pydantic, repaired at most once, and never mutates project state directly.
- **Frontend presentation:** React, Vite, and Fluent UI v9 provide the application shell, forms, editor panels, and accessible controls.
- **Renderer boundary:** PixiJS is contained in renderer adapters. Canonical serializable project state stays outside PixiJS objects and React animation-frame state.
- **API client:** The frontend imports TypeScript types generated from the backend OpenAPI schema and uses Zod for project import validation.
- **Native runtime:** `frontend/src/runtime` plays exported native projects without React, Fluent UI, or editor dependencies.

## Data Flow

```text
Prompt or form
  -> validated request DTO
  -> LLMProvider or deterministic fixture
  -> Pydantic schema validation
  -> deterministic builder/compiler
  -> versioned project document
  -> renderer/runtime projection
```

For motion, the model produces semantic `MotionPlan` data only. The compiler owns timing, tracks, IK-style target solving, contacts, constraints, validation reports, and editable `AnimationClip` output.

## Local-First Operation

The app starts when Ollama is offline. Health, settings, and model-list endpoints report Ollama separately from core application health. Native development binds the backend to `127.0.0.1` by default; exposing the app to a network requires an explicit deployment decision and a separate authentication review.
