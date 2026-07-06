import {
  applyPoint,
  inverse,
  multiply,
  type Affine2,
  type Vec2
} from "./math";
import { computeWorldTransforms, type RigLike } from "./rig";
import type {
  AttachmentDefinition,
  MeshAttachment,
  MeshAttachment as MeshAttachmentSpec
} from "../schemas/project";

type MeshVertexWeight = MeshAttachment["weights"][number]["weights"][number];

export function matrixToAffine(matrix: readonly [number, number, number, number, number, number]): Affine2 {
  const [a, b, c, d, tx, ty] = matrix;
  return { a, b, c, d, tx, ty };
}

export function normalizeVertexWeights(weights: readonly MeshVertexWeight[]): MeshVertexWeight[] {
  const positive = weights.filter((weight) => weight.weight > 0);
  const total = positive.reduce((sum, weight) => sum + weight.weight, 0);
  if (positive.length === 0 || total <= 0) {
    throw new Error("at least one positive mesh weight is required");
  }
  const normalized = positive.map((weight) => ({
    bone_id: weight.bone_id,
    weight: weight.weight / total
  }));
  const correction = 1 - normalized.reduce((sum, weight) => sum + weight.weight, 0);
  normalized[normalized.length - 1] = {
    ...normalized[normalized.length - 1],
    weight: normalized[normalized.length - 1].weight + correction
  };
  return normalized;
}

export function editVertexWeight(
  mesh: MeshAttachmentSpec,
  vertexIndex: number,
  boneId: string,
  value: number
): MeshAttachmentSpec {
  if (vertexIndex < 0 || vertexIndex >= mesh.weights.length) {
    throw new Error("vertex index is outside the mesh");
  }
  const clamped = Math.min(Math.max(value, 0), 1);
  const nextWeights = mesh.weights.map((vertexWeights, index) => {
    if (index !== vertexIndex) {
      return vertexWeights;
    }
    const byBone = new Map(vertexWeights.weights.map((weight) => [weight.bone_id, weight.weight]));
    byBone.set(boneId, clamped);
    return {
      weights: normalizeVertexWeights(
        Array.from(byBone, ([entryBoneId, weight]) => ({ bone_id: entryBoneId, weight }))
      )
    };
  });
  return { ...mesh, weights: nextWeights };
}

export function mirrorBoneId(boneId: string): string {
  if (boneId.endsWith("_l")) {
    return `${boneId.slice(0, -2)}_r`;
  }
  if (boneId.endsWith("_r")) {
    return `${boneId.slice(0, -2)}_l`;
  }
  return boneId;
}

export function mirrorMeshWeights(mesh: MeshAttachmentSpec): MeshAttachmentSpec {
  return {
    ...mesh,
    vertices: mesh.vertices.map(([x, y]) => [x, -y]),
    weights: mesh.weights.map((vertexWeights) => ({
      weights: vertexWeights.weights.map((weight) => ({
        bone_id: mirrorBoneId(weight.bone_id),
        weight: weight.weight
      }))
    })),
    bind_pose: mesh.bind_pose.map((bind) => ({
      ...bind,
      bone_id: mirrorBoneId(bind.bone_id)
    }))
  };
}

export function weightHeatmapColor(weight: number): string {
  const clamped = Math.min(Math.max(weight, 0), 1);
  const red = Math.round(255 * clamped);
  const blue = Math.round(255 * (1 - clamped));
  const green = Math.round(96 * (1 - Math.abs(clamped - 0.5) * 2));
  return `#${red.toString(16).padStart(2, "0")}${green.toString(16).padStart(2, "0")}${blue
    .toString(16)
    .padStart(2, "0")}`;
}

export function skinMeshAttachment(
  attachment: AttachmentDefinition,
  rig: RigLike
): Vec2[] {
  if (attachment.kind !== "mesh" || attachment.mesh === null) {
    throw new Error("skinMeshAttachment requires a mesh attachment");
  }
  const worlds = computeWorldTransforms(rig);
  const ownerWorld = worlds.get(attachment.bone_id);
  if (ownerWorld === undefined) {
    throw new Error(`attachment owner bone '${attachment.bone_id}' is missing`);
  }
  const ownerInverse = inverse(ownerWorld);
  const currentByBone = new Map<string, Affine2>();
  for (const [boneId, world] of worlds) {
    currentByBone.set(boneId, multiply(ownerInverse, world));
  }
  const inverseBindByBone = new Map(
    attachment.mesh.bind_pose.map((bind) => [bind.bone_id, matrixToAffine(bind.inverse_bind_matrix)])
  );

  return attachment.mesh.vertices.map(([x, y], vertexIndex) => {
    let skinned = { x: 0, y: 0 };
    for (const weight of normalizeVertexWeights(attachment.mesh!.weights[vertexIndex].weights)) {
      const current = currentByBone.get(weight.bone_id);
      const inverseBind = inverseBindByBone.get(weight.bone_id);
      if (current === undefined || inverseBind === undefined) {
        throw new Error(`mesh influence bone '${weight.bone_id}' is missing`);
      }
      const transformed = applyPoint(multiply(current, inverseBind), { x, y });
      skinned = {
        x: skinned.x + transformed.x * weight.weight,
        y: skinned.y + transformed.y * weight.weight
      };
    }
    return skinned;
  });
}
