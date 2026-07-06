# Project Format Reference

RigStory Studio archives and project files use the native `rigstory-project` format.

## Top-Level Document

```json
{
  "format": "rigstory-project",
  "schema_version": "0.6.0",
  "engine_version": "0.1.0",
  "project": { "id": "project_demo", "name": "Demo" },
  "characters": [],
  "scenes": [],
  "motion_plans": [],
  "clips": [],
  "asset_manifest": [],
  "generation_records": []
}
```

Rules:

- `schema_version` is explicit and migrated through the backend registry.
- Stable IDs are not reused for different objects.
- Canonical JSON is byte-stable for committed samples.
- Unknown imported fields are preserved where practical by migrations.
- LLM raw attempts and validated records are stored separately in `generation_records`.
- Coordinates are Y-up and rotations are counterclockwise degrees.
- Renderer-specific coordinate conversion happens only in renderer adapters.

## Archives

Portable archives contain a manifest, canonical `project.json`, optional content-addressed assets, and checksums. Import validates zip entry names, rejects traversal, verifies checksums, migrates older project documents, and resolves project-id conflicts according to the selected strategy.
