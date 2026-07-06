# Changelog

## 0.1.0

- Implemented local-first FastAPI and React/Fluent UI shell.
- Added versioned project schema, migrations, canonical JSON, sample validation, and archive import/export.
- Added deterministic 2D math, rig, scene, clip, mesh, and motion-plan domain models.
- Added manual rig editor, PixiJS renderer adapter, timeline playback, visual golden, and native runtime player.
- Added deterministic procedural vector character builder.
- Added Ollama provider boundary, structured character generation, structured motion planning, one-repair validation flow, and generation records.
- Added scene snapshots, colliders, anchors, affordances, plan validation, deterministic compiler, two-character handshake workflow, and export jobs.
- Added release benchmark, prompt/archive-size request limits, release docs, issue templates, and PR checklist.

Known limitations:

- WebM export requires `ffmpeg` on `PATH`.
- The export UI is still API/client oriented rather than a polished panel.
- Accessibility and security audits have evidence for several controls, but the full release audit checklist is not yet closed.
