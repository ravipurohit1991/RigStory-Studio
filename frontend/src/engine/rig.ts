/**
 * Rig hierarchy validation and forward kinematics.
 * Mirrors backend/app/domain/rig.py: bones extend along local +X by
 * `length`; world matrices compose parent-to-child from the single root.
 */

import {
  AFFINE_IDENTITY,
  applyPoint,
  fromTrs,
  multiply,
  type Affine2,
  type Vec2
} from "./math";

export interface ValidationIssue {
  readonly code: string;
  readonly message: string;
  readonly path: string;
}

export interface TransformSpecLike {
  readonly position: readonly [number, number];
  readonly rotation_deg: number;
  readonly scale: readonly [number, number];
}

export interface BoneLike {
  readonly id: string;
  readonly parent_id: string | null;
  readonly setup_transform: TransformSpecLike;
  readonly length: number;
}

export interface RigLike {
  readonly id: string;
  readonly bones: readonly BoneLike[];
}

export function transformToAffine(transform: TransformSpecLike): Affine2 {
  return fromTrs(
    { x: transform.position[0], y: transform.position[1] },
    transform.rotation_deg,
    transform.scale
  );
}

export function validateRig(rig: RigLike, pathPrefix = ""): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const prefix = pathPrefix ? `${pathPrefix}.` : "";

  if (rig.bones.length === 0) {
    issues.push({ code: "RIG_NO_BONES", message: "rig has no bones", path: `${prefix}bones` });
    return issues;
  }

  const byId = new Map<string, BoneLike>();
  rig.bones.forEach((bone, index) => {
    if (byId.has(bone.id)) {
      issues.push({
        code: "RIG_DUPLICATE_BONE_ID",
        message: `bone id '${bone.id}' is defined more than once`,
        path: `${prefix}bones[${index}].id`
      });
    } else {
      byId.set(bone.id, bone);
    }
  });

  const roots = rig.bones.filter((bone) => bone.parent_id === null);
  if (roots.length === 0) {
    issues.push({
      code: "RIG_NO_ROOT",
      message: "no bone has a null parent_id",
      path: `${prefix}bones`
    });
  } else if (roots.length > 1) {
    issues.push({
      code: "RIG_MULTIPLE_ROOTS",
      message: `expected exactly one root bone, found: ${roots.map((bone) => bone.id).join(", ")}`,
      path: `${prefix}bones`
    });
  }

  rig.bones.forEach((bone, index) => {
    if (bone.parent_id === null) {
      return;
    }
    if (bone.parent_id === bone.id) {
      issues.push({
        code: "RIG_SELF_PARENT",
        message: `bone '${bone.id}' is its own parent`,
        path: `${prefix}bones[${index}].parent_id`
      });
    } else if (!byId.has(bone.parent_id)) {
      issues.push({
        code: "RIG_MISSING_PARENT",
        message: `bone '${bone.id}' references unknown parent '${bone.parent_id}'`,
        path: `${prefix}bones[${index}].parent_id`
      });
    }
  });

  // Cycle detection over resolvable parents.
  rig.bones.forEach((bone, index) => {
    const seen = new Set<string>([bone.id]);
    let current = bone;
    while (current.parent_id !== null) {
      const parent = byId.get(current.parent_id);
      if (parent === undefined || parent.id === current.id) {
        break;
      }
      if (seen.has(parent.id)) {
        issues.push({
          code: "RIG_CYCLE",
          message: `bone '${bone.id}' participates in a parent cycle`,
          path: `${prefix}bones[${index}].parent_id`
        });
        break;
      }
      seen.add(parent.id);
      current = parent;
    }
  });

  // Connectivity: every bone must be reachable from the single root.
  const hasCycle = issues.some((issue) => issue.code === "RIG_CYCLE");
  if (roots.length === 1 && !hasCycle) {
    const children = new Map<string, string[]>();
    for (const bone of byId.values()) {
      children.set(bone.id, []);
    }
    for (const bone of byId.values()) {
      if (bone.parent_id !== null && children.has(bone.parent_id)) {
        children.get(bone.parent_id)?.push(bone.id);
      }
    }
    const reachable = new Set<string>();
    const stack = [roots[0].id];
    while (stack.length > 0) {
      const boneId = stack.pop();
      if (boneId === undefined || reachable.has(boneId)) {
        continue;
      }
      reachable.add(boneId);
      stack.push(...(children.get(boneId) ?? []));
    }
    rig.bones.forEach((bone, index) => {
      if (!reachable.has(bone.id)) {
        issues.push({
          code: "RIG_DISCONNECTED_BONE",
          message: `bone '${bone.id}' is not reachable from root '${roots[0].id}'`,
          path: `${prefix}bones[${index}]`
        });
      }
    });
  }

  return issues;
}

/** World matrix per bone from setup transforms, root to leaf. */
export function computeWorldTransforms(rig: RigLike): Map<string, Affine2> {
  const issues = validateRig(rig);
  if (issues.length > 0) {
    throw new Error(`invalid rig: ${issues.map((issue) => issue.code).join(", ")}`);
  }

  const byId = new Map(rig.bones.map((bone) => [bone.id, bone]));
  const children = new Map<string, string[]>(rig.bones.map((bone) => [bone.id, []]));
  let rootId = "";
  for (const bone of rig.bones) {
    if (bone.parent_id === null) {
      rootId = bone.id;
    } else {
      children.get(bone.parent_id)?.push(bone.id);
    }
  }

  const world = new Map<string, Affine2>();
  const stack: Array<[string, Affine2]> = [[rootId, AFFINE_IDENTITY]];
  while (stack.length > 0) {
    const entry = stack.pop();
    if (entry === undefined) {
      break;
    }
    const [boneId, parentWorld] = entry;
    const bone = byId.get(boneId);
    if (bone === undefined) {
      continue;
    }
    const boneWorld = multiply(parentWorld, transformToAffine(bone.setup_transform));
    world.set(boneId, boneWorld);
    for (const childId of children.get(boneId) ?? []) {
      stack.push([childId, boneWorld]);
    }
  }
  return world;
}

export interface BoneEndpoints {
  readonly origin: Vec2;
  readonly tip: Vec2;
}

/** World-space (origin, tip) per bone; the tip lies `length` along local +X. */
export function computeBoneEndpoints(rig: RigLike): Map<string, BoneEndpoints> {
  const world = computeWorldTransforms(rig);
  const byId = new Map(rig.bones.map((bone) => [bone.id, bone]));
  const endpoints = new Map<string, BoneEndpoints>();
  for (const [boneId, matrix] of world) {
    const bone = byId.get(boneId);
    if (bone === undefined) {
      continue;
    }
    endpoints.set(boneId, {
      origin: applyPoint(matrix, { x: 0, y: 0 }),
      tip: applyPoint(matrix, { x: bone.length, y: 0 })
    });
  }
  return endpoints;
}
