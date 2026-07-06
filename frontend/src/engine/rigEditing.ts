import {
  AFFINE_IDENTITY,
  angleDeg,
  applyPoint,
  applyVector,
  inverse,
  length,
  normalizeDeg,
  sub,
  type Affine2,
  type Vec2
} from "./math";
import {
  computeWorldTransforms,
  validateRig,
  type BoneLike,
  type RigLike,
  type TransformSpecLike,
  type ValidationIssue
} from "./rig";

export type RigEditMode = "setup" | "animation";

export interface ReparentResult<TRig extends RigLike> {
  readonly rig: TRig;
  readonly changed: boolean;
  readonly issues: readonly ValidationIssue[];
}

function isFiniteNumber(value: number): boolean {
  return Number.isFinite(value);
}

function transformEquals(a: TransformSpecLike, b: TransformSpecLike): boolean {
  return (
    a.rotation_deg === b.rotation_deg &&
    a.position[0] === b.position[0] &&
    a.position[1] === b.position[1] &&
    a.scale[0] === b.scale[0] &&
    a.scale[1] === b.scale[1]
  );
}

function updateBone<TRig extends RigLike>(
  rig: TRig,
  boneId: string,
  update: (bone: BoneLike) => BoneLike
): TRig {
  let changed = false;
  const bones = rig.bones.map((bone) => {
    if (bone.id !== boneId) {
      return bone;
    }
    const next = update(bone);
    changed = changed || next !== bone;
    return next;
  });
  return changed ? ({ ...rig, bones } as TRig) : rig;
}

function setBoneTransform<TRig extends RigLike>(
  rig: TRig,
  boneId: string,
  transform: TransformSpecLike
): TRig {
  return updateBone(rig, boneId, (bone) => {
    if (transformEquals(bone.setup_transform, transform)) {
      return bone;
    }
    return { ...bone, setup_transform: transform };
  });
}

function parentWorldTransform(rig: RigLike, bone: BoneLike): Affine2 {
  if (bone.parent_id === null) {
    return AFFINE_IDENTITY;
  }
  const parentWorld = computeWorldTransforms(rig).get(bone.parent_id);
  if (parentWorld === undefined) {
    throw new Error(`missing parent world transform for '${bone.parent_id}'`);
  }
  return parentWorld;
}

export function findBone(rig: RigLike, boneId: string): BoneLike | null {
  return rig.bones.find((bone) => bone.id === boneId) ?? null;
}

export function getDescendantBoneIds(rig: RigLike, boneId: string): Set<string> {
  const childrenByParent = new Map<string, string[]>();
  for (const bone of rig.bones) {
    if (bone.parent_id === null) {
      continue;
    }
    childrenByParent.set(bone.parent_id, [...(childrenByParent.get(bone.parent_id) ?? []), bone.id]);
  }

  const descendants = new Set<string>();
  const stack = [...(childrenByParent.get(boneId) ?? [])];
  while (stack.length > 0) {
    const current = stack.pop();
    if (current === undefined || descendants.has(current)) {
      continue;
    }
    descendants.add(current);
    stack.push(...(childrenByParent.get(current) ?? []));
  }
  return descendants;
}

export function setBoneLocalPosition<TRig extends RigLike>(
  rig: TRig,
  boneId: string,
  position: readonly [number, number]
): TRig {
  if (!isFiniteNumber(position[0]) || !isFiniteNumber(position[1])) {
    return rig;
  }
  const bone = findBone(rig, boneId);
  if (bone === null) {
    return rig;
  }
  return setBoneTransform(rig, boneId, {
    ...bone.setup_transform,
    position: [position[0], position[1]]
  });
}

export function setBoneLocalRotation<TRig extends RigLike>(
  rig: TRig,
  boneId: string,
  rotationDeg: number
): TRig {
  if (!isFiniteNumber(rotationDeg)) {
    return rig;
  }
  const bone = findBone(rig, boneId);
  if (bone === null) {
    return rig;
  }
  return setBoneTransform(rig, boneId, {
    ...bone.setup_transform,
    rotation_deg: normalizeDeg(rotationDeg)
  });
}

export function setBoneLength<TRig extends RigLike>(
  rig: TRig,
  boneId: string,
  lengthValue: number
): TRig {
  if (!isFiniteNumber(lengthValue)) {
    return rig;
  }
  const nextLength = Math.max(0, lengthValue);
  return updateBone(rig, boneId, (bone) =>
    bone.length === nextLength ? bone : { ...bone, length: nextLength }
  );
}

export function reparentBone<TRig extends RigLike>(
  rig: TRig,
  boneId: string,
  parentId: string | null
): ReparentResult<TRig> {
  if (parentId === boneId) {
    return {
      rig,
      changed: false,
      issues: [
        {
          code: "RIG_SELF_PARENT",
          message: `bone '${boneId}' cannot be its own parent`,
          path: "bones.parent_id"
        }
      ]
    };
  }

  if (parentId !== null && getDescendantBoneIds(rig, boneId).has(parentId)) {
    return {
      rig,
      changed: false,
      issues: [
        {
          code: "RIG_CYCLE",
          message: `reparenting '${boneId}' under descendant '${parentId}' would create a cycle`,
          path: "bones.parent_id"
        }
      ]
    };
  }

  const nextRig = updateBone(rig, boneId, (bone) =>
    bone.parent_id === parentId ? bone : { ...bone, parent_id: parentId }
  );
  if (nextRig === rig) {
    return { rig, changed: false, issues: [] };
  }

  const issues = validateRig(nextRig);
  if (issues.length > 0) {
    return { rig, changed: false, issues };
  }
  return { rig: nextRig, changed: true, issues: [] };
}

export function editBoneEndpointToWorldPoint<TRig extends RigLike>(
  rig: TRig,
  boneId: string,
  worldPoint: Vec2,
  options: {
    readonly mode: RigEditMode;
    readonly allowLength: boolean;
    readonly minLength?: number;
  }
): TRig {
  const bone = findBone(rig, boneId);
  if (bone === null) {
    return rig;
  }

  const parentWorld = parentWorldTransform(rig, bone);
  const parentLocalTarget = applyPoint(inverse(parentWorld), worldPoint);
  const localVector = {
    x: parentLocalTarget.x - bone.setup_transform.position[0],
    y: parentLocalTarget.y - bone.setup_transform.position[1]
  };
  const localDistance = length(localVector);
  if (localDistance <= 1e-9) {
    return rig;
  }

  const rotationDeg = angleDeg(localVector);
  const nextTransform = {
    ...bone.setup_transform,
    rotation_deg: normalizeDeg(rotationDeg)
  };
  const canEditLength = options.mode === "setup" && options.allowLength;
  const scaleX = Math.abs(bone.setup_transform.scale[0]);
  const nextLength =
    canEditLength && scaleX > 1e-9
      ? Math.max(options.minLength ?? 0, localDistance / scaleX)
      : bone.length;

  return updateBone(rig, boneId, (currentBone) => {
    const transformChanged = !transformEquals(currentBone.setup_transform, nextTransform);
    const lengthChanged = currentBone.length !== nextLength;
    if (!transformChanged && !lengthChanged) {
      return currentBone;
    }
    return {
      ...currentBone,
      setup_transform: nextTransform,
      length: nextLength
    };
  });
}

export function editBoneBodyByWorldDelta<TRig extends RigLike>(
  rigAtDragStart: TRig,
  boneId: string,
  startWorldPoint: Vec2,
  currentWorldPoint: Vec2,
  options: { readonly mode: RigEditMode }
): TRig {
  if (options.mode !== "setup") {
    return rigAtDragStart;
  }
  const bone = findBone(rigAtDragStart, boneId);
  if (bone === null) {
    return rigAtDragStart;
  }

  const parentWorld = parentWorldTransform(rigAtDragStart, bone);
  const worldDelta = sub(currentWorldPoint, startWorldPoint);
  const localDelta = applyVector(inverse(parentWorld), worldDelta);
  return setBoneLocalPosition(rigAtDragStart, boneId, [
    bone.setup_transform.position[0] + localDelta.x,
    bone.setup_transform.position[1] + localDelta.y
  ]);
}
