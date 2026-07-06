import { describe, expect, it } from "vitest";

import {
  BUILDER_PRESETS,
  buildProceduralCharacter,
  characterBuilderRequestSchema,
  createGeneratedCharacterProjectDocument,
  regenerateCharacterRegion
} from "./characterBuilder";
import type { CharacterProportions } from "./characterBuilder";
import { validateRig } from "./rig";
import { projectDocumentSchema } from "../schemas/project";

const REQUIRED_BONES = new Set([
  "root",
  "hips",
  "spine_lower",
  "spine_upper",
  "chest",
  "neck",
  "head",
  "eye_l",
  "eye_r",
  "clavicle_l",
  "upper_arm_l",
  "forearm_l",
  "hand_l",
  "thigh_l",
  "shin_l",
  "foot_l",
  "toe_l",
  "clavicle_r",
  "upper_arm_r",
  "forearm_r",
  "hand_r",
  "thigh_r",
  "shin_r",
  "foot_r",
  "toe_r"
]);

describe("character builder", () => {
  it("generates valid editable characters for the diverse preset fixtures", () => {
    expect(BUILDER_PRESETS.length).toBeGreaterThanOrEqual(10);

    for (const request of BUILDER_PRESETS) {
      const result = buildProceduralCharacter(request);
      const boneIds = new Set(result.character.rig.bones.map((bone) => bone.id));
      const attachmentIds = new Set(result.character.attachments.map((part) => part.id));

      expect(result.diagnostics.some((diagnostic) => diagnostic.severity === "error")).toBe(false);
      expect(validateRig(result.character.rig)).toEqual([]);
      expect(boneIds).toEqual(REQUIRED_BONES);
      expect(new Set(result.constraints.map((constraint) => constraint.id))).toEqual(
        new Set(["ik_arm_l", "ik_arm_r", "ik_leg_l", "ik_leg_r", "look_eyes", "look_head"])
      );
      expect(result.character.attachments.length).toBeGreaterThanOrEqual(25);
      expect(attachmentIds.has("part_head")).toBe(true);
      expect(attachmentIds.has("part_torso")).toBe(true);
      expect(attachmentIds.has("part_eye_l")).toBe(true);
      expect(attachmentIds.has("part_eye_r")).toBe(true);
      expect(result.character.attachments.every((part) => boneIds.has(part.bone_id))).toBe(true);
      expect(
        result.character.attachments.every(
          (part) =>
            (part.kind === "primitive" &&
              part.primitive !== null &&
              part.primitive.size[0] > 0 &&
              part.primitive.size[1] > 0) ||
            (part.kind === "mesh" &&
              part.mesh !== null &&
              part.mesh.vertices.length >= 3 &&
              part.mesh.weights.every(
                (vertex) =>
                  Math.abs(vertex.weights.reduce((sum, weight) => sum + weight.weight, 0) - 1) <=
                  1e-6
              ))
        )
      ).toBe(true);
    }
  });

  it("is deterministic for identical normalized input", () => {
    const request = BUILDER_PRESETS[0];

    const first = buildProceduralCharacter(request);
    const second = buildProceduralCharacter(request);

    expect(first.character.id).toBe(second.character.id);
    expect(first.character.rig.id).toBe(second.character.rig.id);
    expect(first.constraints).toEqual(second.constraints);
    expect(JSON.stringify(first.character)).toBe(JSON.stringify(second.character));
  });

  it("clamps out-of-range proportions before building", () => {
    const request = characterBuilderRequestSchema.parse({
      name: "Clamp",
      proportions: {
        shoulder_width: -2,
        torso_length: 5,
        waist_width: 0,
        hip_width: 3,
        arm_length: 0.1,
        leg_length: 4,
        head_size: Number.POSITIVE_INFINITY,
        asymmetry: -1
      } satisfies Partial<CharacterProportions>
    });

    const result = buildProceduralCharacter(request);
    const codes = new Set(result.diagnostics.map((diagnostic) => diagnostic.code));

    expect(codes.has("REQUEST_CLAMPED_VALUE")).toBe(true);
    expect(codes.has("REQUEST_NONFINITE_VALUE")).toBe(true);
    expect(result.normalizedRequest.proportions.shoulder_width).toBe(0.75);
    expect(result.normalizedRequest.proportions.torso_length).toBe(1.18);
    expect(result.normalizedRequest.proportions.head_size).toBe(1);
    expect(validateRig(result.character.rig)).toEqual([]);
  });

  it("regenerates a single visual region without changing the rig", () => {
    const first = buildProceduralCharacter(BUILDER_PRESETS[0]).character;
    const nextRequest = {
      ...BUILDER_PRESETS[0],
      palette: { ...BUILDER_PRESETS[0].palette, hair: "#ff00aa" }
    };

    const updated = regenerateCharacterRegion(nextRequest, first, "hair");
    const hair = updated.attachments.find((part) => part.id === "part_hair_front");

    expect(JSON.stringify(updated.rig)).toBe(JSON.stringify(first.rig));
    expect(hair?.primitive?.fill).toBe("#ff00aa");
    expect(updated.attachments.find((part) => part.id === "part_torso")?.primitive?.fill).toBe(
      first.attachments.find((part) => part.id === "part_torso")?.primitive?.fill
    );
  });

  it("creates a valid project document for saving a generated character", () => {
    const character = buildProceduralCharacter(BUILDER_PRESETS[2]).character;
    const document = createGeneratedCharacterProjectDocument(character, "test_save");

    expect(projectDocumentSchema.parse(document).characters[0].id).toBe(character.id);
    expect(document.project.id).toBe("project_builder_test_save");
  });
});
