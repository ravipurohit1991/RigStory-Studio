import { describe, expect, it } from "vitest";

import { readSample } from "../test-utils/samples";
import { validateProjectDocument } from "./invariants";
import { projectDocumentSchema, sceneSchema } from "./project";

const VALID_PROJECT_SAMPLES = [
  "projects/empty-project.rigstory.json",
  "projects/biped-demo.rigstory.json",
  "projects/generated-character.rigstory.json"
];

const SCENE_FIXTURES = [
  "fixtures/scene-empty.json",
  "fixtures/scene-one-character.json",
  "fixtures/scene-two-characters.json"
];

describe("shared project samples", () => {
  it.each(VALID_PROJECT_SAMPLES)("%s parses and passes invariants", (relativePath) => {
    const document = projectDocumentSchema.parse(readSample(relativePath));
    expect(validateProjectDocument(document)).toEqual([]);
  });

  it("parses the biped demo with the expected contents", () => {
    const document = projectDocumentSchema.parse(readSample("projects/biped-demo.rigstory.json"));
    expect(document.characters).toHaveLength(2);
    expect(document.scenes).toHaveLength(3);
    expect(document.clips).toHaveLength(1);
    expect(document.scenes.map((scene) => scene.actors.length).sort()).toEqual([0, 1, 2]);
  });

  it("parses a generated character project with its generation record", () => {
    const document = projectDocumentSchema.parse(
      readSample("projects/generated-character.rigstory.json")
    );
    expect(document.generation_records).toHaveLength(1);
    const record = document.generation_records[0];
    expect(record.character_id).toBe(document.characters[0].id);
    expect(record.status).toBe("succeeded");
    expect(record.blueprint).not.toBeNull();
  });
});

describe("shared scene fixtures", () => {
  it.each(SCENE_FIXTURES)("%s parses", (relativePath) => {
    const scene = sceneSchema.parse(readSample(relativePath));
    expect(scene.actors.length).toBeLessThanOrEqual(2);
  });
});

describe("invalid samples are rejected", () => {
  it("rejects three actors at parse time", () => {
    const raw = readSample("invalid/project-three-actors.rigstory.json");
    expect(() => projectDocumentSchema.parse(raw)).toThrow();
  });

  it("rejects an unsupported future schema version", () => {
    const raw = readSample("invalid/project-future-version.rigstory.json");
    expect(() => projectDocumentSchema.parse(raw)).toThrow();
  });

  it("rejects inverted joint limits at parse time", () => {
    const raw = readSample("invalid/project-inverted-joint-limit.rigstory.json");
    expect(() => projectDocumentSchema.parse(raw)).toThrow();
  });

  it("flags bad references with the same codes as the backend", () => {
    const document = projectDocumentSchema.parse(readSample("invalid/project-bad-refs.rigstory.json"));
    const codes = validateProjectDocument(document).map((issue) => issue.code);
    expect(codes).toContain("CLIP_UNKNOWN_BONE");
    expect(codes).toContain("CLIP_KEYFRAME_ORDER");
  });

  it("flags dangling character references", () => {
    const raw = readSample("projects/biped-demo.rigstory.json") as Record<string, unknown>;
    const document = projectDocumentSchema.parse({ ...raw, characters: [] });
    const codes = validateProjectDocument(document).map((issue) => issue.code);
    expect(codes).toContain("SCENE_UNKNOWN_CHARACTER");
  });

  it("flags invalid clip loop ranges", () => {
    const raw = readSample("projects/biped-demo.rigstory.json") as Record<string, unknown>;
    const clips = [...(raw.clips as Record<string, unknown>[])];
    clips[0] = { ...clips[0], loop_range: [0.8, 0.2] };
    const document = projectDocumentSchema.parse({ ...raw, clips });
    const codes = validateProjectDocument(document).map((issue) => issue.code);
    expect(codes).toContain("CLIP_LOOP_RANGE_INVALID");
  });
});

describe("legacy documents", () => {
  it("does not accept 0.1.0 documents without migration", () => {
    const raw = readSample("migrations/empty-project-0.1.0.rigstory.json");
    // The import layer supports only the current version; migration is a
    // backend responsibility in this phase.
    expect(() => projectDocumentSchema.parse(raw)).toThrow();
  });
});
