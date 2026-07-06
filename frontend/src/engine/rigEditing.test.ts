import { describe, expect, it } from "vitest";

import { rigSchema, type RigDefinition } from "../schemas/project";
import { readSample } from "../test-utils/samples";
import {
  editBoneBodyByWorldDelta,
  editBoneEndpointToWorldPoint,
  getDescendantBoneIds,
  reparentBone,
  setBoneLength,
  setBoneLocalPosition,
  setBoneLocalRotation
} from "./rigEditing";

function loadRig(relativePath: string): RigDefinition {
  return rigSchema.parse(readSample(relativePath));
}

function rootThreeBoneRig(): RigDefinition {
  return {
    id: "rig_three_bone",
    name: "Three-bone rig",
    bones: [
      {
        id: "root",
        parent_id: null,
        setup_transform: { position: [0, 0], rotation_deg: 0, scale: [1, 1] },
        length: 1,
        joint_limit: null,
        tags: []
      },
      {
        id: "child_a",
        parent_id: "root",
        setup_transform: { position: [1, 0], rotation_deg: 0, scale: [1, 1] },
        length: 1,
        joint_limit: null,
        tags: []
      },
      {
        id: "child_b",
        parent_id: "root",
        setup_transform: { position: [0, 1], rotation_deg: 0, scale: [1, 1] },
        length: 1,
        joint_limit: null,
        tags: []
      }
    ]
  };
}

describe("rig editing helpers", () => {
  it("edits local setup values immutably", () => {
    const rig = loadRig("fixtures/rig-two-bone.json");
    const positioned = setBoneLocalPosition(rig, "bone_a", [2, 3]);
    const rotated = setBoneLocalRotation(positioned, "bone_a", 450);
    const resized = setBoneLength(rotated, "bone_a", -5);

    expect(rig.bones[0].setup_transform.position).toEqual([0, 0]);
    expect(positioned.bones[0].setup_transform.position).toEqual([2, 3]);
    expect(rotated.bones[0].setup_transform.rotation_deg).toBe(90);
    expect(resized.bones[0].length).toBe(0);
  });

  it("drags endpoints to rotation and optional setup length", () => {
    const rig = loadRig("fixtures/rig-two-bone.json");
    const stretched = editBoneEndpointToWorldPoint(rig, "bone_a", { x: 0, y: 12 }, {
      mode: "setup",
      allowLength: true
    });

    expect(stretched.bones[0].setup_transform.rotation_deg).toBeCloseTo(90);
    expect(stretched.bones[0].length).toBeCloseTo(12);

    const rotatedOnly = editBoneEndpointToWorldPoint(rig, "bone_a", { x: 0, y: 12 }, {
      mode: "animation",
      allowLength: true
    });

    expect(rotatedOnly.bones[0].setup_transform.rotation_deg).toBeCloseTo(90);
    expect(rotatedOnly.bones[0].length).toBe(10);
  });

  it("drags bone bodies through parent-local setup translation only in setup mode", () => {
    const rig = loadRig("fixtures/rig-two-bone.json");
    const moved = editBoneBodyByWorldDelta(
      rig,
      "bone_a",
      { x: 1, y: 1 },
      { x: 3, y: 4 },
      { mode: "setup" }
    );

    expect(moved.bones[0].setup_transform.position).toEqual([2, 3]);
    expect(editBoneBodyByWorldDelta(rig, "bone_a", { x: 1, y: 1 }, { x: 3, y: 4 }, {
      mode: "animation"
    })).toBe(rig);
  });

  it("reparents valid bones and prevents cycles", () => {
    const rig = rootThreeBoneRig();
    const reparented = reparentBone(rig, "child_b", "child_a");

    expect(reparented.changed).toBe(true);
    expect(reparented.rig.bones.find((bone) => bone.id === "child_b")?.parent_id).toBe("child_a");
    expect(getDescendantBoneIds(reparented.rig, "root")).toEqual(new Set(["child_a", "child_b"]));

    const rejected = reparentBone(reparented.rig, "child_a", "child_b");
    expect(rejected.changed).toBe(false);
    expect(rejected.issues.map((issue) => issue.code)).toContain("RIG_CYCLE");
    expect(rejected.rig).toBe(reparented.rig);
  });
});
