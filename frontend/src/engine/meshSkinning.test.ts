import { describe, expect, it } from "vitest";

import { BUILDER_PRESETS, buildProceduralCharacter } from "./characterBuilder";
import {
  editVertexWeight,
  mirrorBoneId,
  normalizeVertexWeights,
  skinMeshAttachment,
  weightHeatmapColor
} from "./meshSkinning";

describe("weighted mesh skinning", () => {
  it("skins generated sleeve meshes deterministically", () => {
    const result = buildProceduralCharacter({ ...BUILDER_PRESETS[1], top: "jacket" });
    const sleeve = result.character.attachments.find((part) => part.id === "mesh_sleeve_l");

    expect(sleeve?.kind).toBe("mesh");
    const first = skinMeshAttachment(sleeve!, result.character.rig);
    const second = skinMeshAttachment(sleeve!, result.character.rig);

    expect(first).toEqual(second);
    expect(first).toHaveLength(sleeve!.mesh!.vertices.length);
    expect(first[0].x).toBeCloseTo(sleeve!.mesh!.vertices[0][0]);
    expect(first[0].y).toBeCloseTo(sleeve!.mesh!.vertices[0][1]);
  });

  it("normalizes, edits, mirrors, and colors weights for the editor", () => {
    const normalized = normalizeVertexWeights([
      { bone_id: "upper_arm_l", weight: 2 },
      { bone_id: "forearm_l", weight: 1 }
    ]);

    expect(normalized.reduce((sum, weight) => sum + weight.weight, 0)).toBeCloseTo(1);
    expect(mirrorBoneId("forearm_l")).toBe("forearm_r");
    expect(weightHeatmapColor(1)).toBe("#ff0000");
    expect(weightHeatmapColor(0)).toBe("#0000ff");

    const result = buildProceduralCharacter({ ...BUILDER_PRESETS[1], top: "jacket" });
    const sleeve = result.character.attachments.find((part) => part.id === "mesh_sleeve_l");
    const edited = editVertexWeight(sleeve!.mesh!, 2, "upper_arm_l", 0.75);
    const editedTotal = edited.weights[2].weights.reduce((sum, weight) => sum + weight.weight, 0);

    expect(editedTotal).toBeCloseTo(1);
    expect(edited.weights[2].weights.some((weight) => weight.bone_id === "upper_arm_l")).toBe(true);
  });
});
