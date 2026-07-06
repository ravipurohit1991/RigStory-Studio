import { describe, expect, it } from "vitest";

import bipedProjectJson from "@samples/projects/biped-demo.rigstory.json";
import { projectDocumentSchema } from "../schemas/project";
import { evaluateClip } from "./clip";
import { exportClipJson, exportRigidAnimatedSvg, importClipJson } from "./clipExport";

const document = projectDocumentSchema.parse(bipedProjectJson);
const clip = document.clips[0];
const character = document.characters[0];

describe("clip export", () => {
  it("exports and imports native clip JSON with identical evaluated poses", () => {
    const exported = exportClipJson(clip);
    const imported = importClipJson(exported);

    expect(imported).toEqual(clip);
    for (const time of [0, 0.3, 0.6, 1.2]) {
      expect(evaluateClip(imported, time)).toEqual(evaluateClip(clip, time));
    }
  });

  it("exports a basic animated SVG for rigid skeleton playback", () => {
    const svg = exportRigidAnimatedSvg({ clip, character, actorId: "actor_mira" });

    expect(svg).toContain("<svg");
    expect(svg).toContain("animateTransform");
    expect(svg).toContain("bone_forearm_r");
    expect(svg).toContain("Seated wave");
  });
});
