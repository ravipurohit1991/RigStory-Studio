# License Provenance Notes

RigStory Studio is an independent implementation. The references named in `specs.md` inform architecture and product behavior only.

## Reference Repositories

- `GenielabsOpenSource/spine-animation-ai`: PolyForm Noncommercial 1.0.0. Do not copy source code.
- `frycz/skeleton-rig`: no license file was found during the specification review. Do not copy source code without confirmed permission.
- `fastapi/full-stack-fastapi-template`: used as architectural inspiration for FastAPI, SQLModel, Docker, tests, and generated-client patterns.
- `microsoft/fluentui`: approved UI component system.
- PixiJS, Ollama docs, and related official documentation are used through their public APIs and docs.

## Dependency Process

CI produces backend and frontend license reports. New required runtime dependencies need a short note in `docs/dependency-licenses.md` explaining why they are necessary and why their license is compatible with the intended release.
