# Dependency License And Provenance Process

RigStory Studio prefers permissively licensed, maintained dependencies and records license reports as CI artifacts. Reference repositories listed in `specs.md` are used for behavior and architecture research only; their source code is not copied into this project.

Backend report:

```powershell
cd backend
python -m pip install -e ".[dev]"
pip-licenses --format=json --output-file backend-license-report.json
```

Frontend report:

```powershell
cd frontend
npm install
npm run license:report
```

Before adding a new required runtime dependency, record why it is needed, confirm that it is compatible with the product's intended licensing, and update [license provenance notes](license-provenance.md).

## Required runtime dependency notes

- `pixi.js` is required for Phase 2 renderer work. The product specification and ADR 0003 choose PixiJS as the rendering adapter behind the React UI while keeping canonical project state renderer-independent. Version 8.19.0 is MIT licensed.
- `Pillow` is required for Phase 11 PNG sequence, animated SVG frame embedding, and WebM frame preparation in the backend media exporter. Pillow is actively maintained and uses a permissive HPND-style license.
