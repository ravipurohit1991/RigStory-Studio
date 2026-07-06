import fixtureRequests from "@samples/fixtures/character-builder-requests.json";
import { z } from "zod";

import {
  PROJECT_SCHEMA_VERSION,
  projectDocumentSchema,
  type AttachmentDefinition,
  type BoneDefinition,
  type CharacterDefinition,
  type ProjectDocument,
  type RigDefinition
} from "../schemas/project";
import { inverse, multiply, type Affine2 } from "./math";
import { computeWorldTransforms } from "./rig";

export const GENERATOR_VERSION = "procedural-human-v1";

const hexColor = z.string().regex(/^#[0-9a-fA-F]{6}$/);
const numericParameter = z.custom<number>((value): value is number => typeof value === "number");

const DEFAULT_PROPORTIONS = {
  shoulder_width: 1,
  torso_length: 1,
  waist_width: 1,
  hip_width: 1,
  arm_length: 1,
  leg_length: 1,
  head_size: 1,
  asymmetry: 0
};

const DEFAULT_PALETTE = {
  skin: "#c98f62",
  hair: "#3d2a1e",
  top: "#2f6f73",
  bottom: "#2f3a56",
  shoes: "#2b2b2b",
  accent: "#f0d36b"
};

export const characterProportionsSchema = z
  .strictObject({
    shoulder_width: numericParameter.default(1),
    torso_length: numericParameter.default(1),
    waist_width: numericParameter.default(1),
    hip_width: numericParameter.default(1),
    arm_length: numericParameter.default(1),
    leg_length: numericParameter.default(1),
    head_size: numericParameter.default(1),
    asymmetry: numericParameter.default(0)
  })
  .default(DEFAULT_PROPORTIONS);

export const characterPaletteSchema = z
  .strictObject({
    skin: hexColor.default("#c98f62"),
    hair: hexColor.default("#3d2a1e"),
    top: hexColor.default("#2f6f73"),
    bottom: hexColor.default("#2f3a56"),
    shoes: hexColor.default("#2b2b2b"),
    accent: hexColor.default("#f0d36b")
  })
  .default(DEFAULT_PALETTE);

export const characterBuilderRequestSchema = z.strictObject({
  name: z.string().min(1).default("Procedural Human"),
  presentation: z.enum(["masculine", "feminine", "neutral"]).default("neutral"),
  age_category: z.enum(["child", "teen", "adult", "older_adult"]).default("adult"),
  height: z.enum(["short", "average", "tall"]).default("average"),
  build: z.enum(["slender", "average", "sturdy", "broad"]).default("average"),
  proportions: characterProportionsSchema,
  palette: characterPaletteSchema,
  hair_style: z.enum(["bald", "short", "bob", "curly", "long", "coily"]).default("short"),
  face_shape: z.enum(["round", "oval", "square", "heart", "long"]).default("oval"),
  top: z.enum(["tshirt", "shirt", "sweater", "jacket"]).default("tshirt"),
  bottom: z.enum(["trousers", "shorts", "skirt"]).default("trousers"),
  footwear: z.enum(["shoes", "boots", "sneakers"]).default("shoes"),
  outerwear: z.enum(["none", "vest", "coat"]).default("none"),
  style: z
    .enum(["flat_vector", "cartoon", "graphic_novel", "paper_cutout", "silhouette"])
    .default("flat_vector")
});

export type CharacterBuilderRequest = z.infer<typeof characterBuilderRequestSchema>;
export type CharacterProportions = z.infer<typeof characterProportionsSchema>;
export type CharacterBuilderRegion = "all" | "hair" | "face" | "clothing";

export interface BuilderDiagnostic {
  readonly code: string;
  readonly severity: "info" | "warning" | "error";
  readonly message: string;
  readonly path: string;
  readonly originalValue?: number | string;
  readonly normalizedValue?: number | string;
}

export interface GeneratedConstraintDefinition {
  readonly id: string;
  readonly type: "two_bone_ik" | "look_at";
  readonly bone_ids: readonly string[];
  readonly effector_bone_id: string;
  readonly tags: readonly string[];
}

export interface CharacterBuilderResult {
  readonly generatorVersion: string;
  readonly normalizedRequest: CharacterBuilderRequest;
  readonly character: CharacterDefinition;
  readonly constraints: readonly GeneratedConstraintDefinition[];
  readonly diagnostics: readonly BuilderDiagnostic[];
}

interface NumericRange {
  readonly path: keyof CharacterBuilderRequest["proportions"];
  readonly min: number;
  readonly defaultValue: number;
  readonly max: number;
}

interface HumanDimensions {
  readonly heightScale: number;
  readonly hipY: number;
  readonly hipLength: number;
  readonly pelvisWidth: number;
  readonly waistWidth: number;
  readonly shoulderWidth: number;
  readonly torsoLower: number;
  readonly torsoUpper: number;
  readonly chestLength: number;
  readonly neckLength: number;
  readonly headLength: number;
  readonly headWidth: number;
  readonly clavicleLength: number;
  readonly upperArmLength: number;
  readonly forearmLength: number;
  readonly handLength: number;
  readonly thighLength: number;
  readonly shinLength: number;
  readonly footLength: number;
  readonly toeLength: number;
  readonly armThickness: number;
  readonly legThickness: number;
  readonly sideAsymmetry: number;
}

const PROPORTION_RANGES: readonly NumericRange[] = [
  { path: "shoulder_width", min: 0.75, defaultValue: 1, max: 1.25 },
  { path: "torso_length", min: 0.82, defaultValue: 1, max: 1.18 },
  { path: "waist_width", min: 0.72, defaultValue: 1, max: 1.18 },
  { path: "hip_width", min: 0.75, defaultValue: 1, max: 1.25 },
  { path: "arm_length", min: 0.84, defaultValue: 1, max: 1.18 },
  { path: "leg_length", min: 0.84, defaultValue: 1, max: 1.2 },
  { path: "head_size", min: 0.86, defaultValue: 1, max: 1.16 },
  { path: "asymmetry", min: 0, defaultValue: 0, max: 0.04 }
];

export const BUILDER_PRESETS: readonly CharacterBuilderRequest[] =
  characterBuilderRequestSchema.array().parse(fixtureRequests.requests);

export const DEFAULT_CHARACTER_REQUEST: CharacterBuilderRequest =
  characterBuilderRequestSchema.parse({});

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`)
    .join(",")}}`;
}

function stableSuffix(request: CharacterBuilderRequest): string {
  const payload = `${GENERATOR_VERSION}:${stableStringify(request)}`;
  let hash = 0x811c9dc5;
  for (let index = 0; index < payload.length; index += 1) {
    hash ^= payload.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}

function round6(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}

function sideFactor(side: "l" | "r", asymmetry: number): number {
  return 1 + (side === "l" ? asymmetry / 2 : -asymmetry / 2);
}

function ageScale(ageCategory: CharacterBuilderRequest["age_category"]): number {
  return { child: 0.74, teen: 0.9, adult: 1, older_adult: 0.97 }[ageCategory];
}

function heightScale(height: CharacterBuilderRequest["height"]): number {
  return { short: 0.92, average: 1, tall: 1.1 }[height];
}

function buildWidthScale(build: CharacterBuilderRequest["build"]): number {
  return { slender: 0.88, average: 1, sturdy: 1.1, broad: 1.2 }[build];
}

function presentationScales(
  presentation: CharacterBuilderRequest["presentation"]
): readonly [number, number, number] {
  if (presentation === "masculine") {
    return [1.08, 1, 0.96];
  }
  if (presentation === "feminine") {
    return [0.96, 0.9, 1.08];
  }
  return [1, 0.97, 1];
}

export function normalizeCharacterBuilderRequest(request: CharacterBuilderRequest): {
  readonly request: CharacterBuilderRequest;
  readonly diagnostics: readonly BuilderDiagnostic[];
} {
  const diagnostics: BuilderDiagnostic[] = [];
  const nextProportions = { ...request.proportions };
  for (const range of PROPORTION_RANGES) {
    const raw = request.proportions[range.path];
    let next = raw;
    if (!Number.isFinite(raw)) {
      next = range.defaultValue;
      diagnostics.push({
        code: "REQUEST_NONFINITE_VALUE",
        severity: "warning",
        message: `${range.path} was non-finite and was reset to its default`,
        path: `proportions.${range.path}`,
        originalValue: String(raw),
        normalizedValue: next
      });
    } else {
      next = Math.min(Math.max(raw, range.min), range.max);
      if (next !== raw) {
        diagnostics.push({
          code: "REQUEST_CLAMPED_VALUE",
          severity: "info",
          message: `${range.path} was clamped into the supported range`,
          path: `proportions.${range.path}`,
          originalValue: raw,
          normalizedValue: next
        });
      }
    }
    nextProportions[range.path] = next;
  }
  return {
    request: { ...request, proportions: nextProportions },
    diagnostics
  };
}

function dimensions(request: CharacterBuilderRequest): HumanDimensions {
  const p = request.proportions;
  const scale = ageScale(request.age_category) * heightScale(request.height);
  const [shoulderShape, waistShape, hipShape] = presentationScales(request.presentation);
  const widthScale = buildWidthScale(request.build);
  const headAge = request.age_category === "child" ? 1.16 : request.age_category === "teen" ? 1.06 : 1;
  const limbAge = request.age_category === "child" ? 0.9 : request.age_category === "teen" ? 0.97 : 1;
  const torsoLower = 0.3 * scale * p.torso_length;
  const torsoUpper = 0.32 * scale * p.torso_length;
  const thigh = 0.82 * scale * p.leg_length * limbAge;
  const shin = 0.74 * scale * p.leg_length * limbAge;
  const shoulderWidth = 0.64 * scale * p.shoulder_width * shoulderShape * widthScale;
  const limbThickness = 0.15 * scale * widthScale;
  return {
    heightScale: scale,
    hipY: thigh + shin + 0.12 * scale,
    hipLength: 0.2 * scale,
    pelvisWidth: 0.5 * scale * p.hip_width * hipShape * widthScale,
    waistWidth: 0.42 * scale * p.waist_width * waistShape * widthScale,
    shoulderWidth,
    torsoLower,
    torsoUpper,
    chestLength: 0.34 * scale * p.torso_length,
    neckLength: 0.14 * scale,
    headLength: 0.42 * scale * p.head_size * headAge,
    headWidth: 0.36 * scale * p.head_size * headAge,
    clavicleLength: Math.max(0.16 * scale, shoulderWidth * 0.36),
    upperArmLength: 0.52 * scale * p.arm_length * limbAge,
    forearmLength: 0.48 * scale * p.arm_length * limbAge,
    handLength: 0.19 * scale,
    thighLength: thigh,
    shinLength: shin,
    footLength: 0.3 * scale,
    toeLength: 0.12 * scale,
    armThickness: limbThickness * 0.82,
    legThickness: limbThickness * 1.12,
    sideAsymmetry: p.asymmetry
  };
}

function jointLimit(min: number, max: number) {
  return { min_rotation_deg: min, max_rotation_deg: max, soft_zone_deg: 0 };
}

function bone(
  id: string,
  parentId: string | null,
  position: readonly [number, number],
  rotationDeg: number,
  length: number,
  tags: readonly string[] = [],
  limit: ReturnType<typeof jointLimit> | null = null
): BoneDefinition {
  return {
    id,
    parent_id: parentId,
    setup_transform: { position: [round6(position[0]), round6(position[1])], rotation_deg: rotationDeg, scale: [1, 1] },
    length: round6(length),
    joint_limit: limit,
    tags: [...tags]
  };
}

export function generateCanonicalHumanRig(request: CharacterBuilderRequest): RigDefinition {
  const dims = dimensions(request);
  const shoulderY = dims.shoulderWidth / 2;
  const hipY = dims.pelvisWidth / 2;
  const eyeY = dims.headWidth * 0.22;
  const bones: BoneDefinition[] = [
    bone("root", null, [0, 0], 0, 0),
    bone("hips", "root", [0, dims.hipY], 90, dims.hipLength, ["core"]),
    bone("spine_lower", "hips", [dims.hipLength, 0], 0, dims.torsoLower, ["core"], jointLimit(-30, 30)),
    bone("spine_upper", "spine_lower", [dims.torsoLower, 0], 0, dims.torsoUpper, ["core"], jointLimit(-32, 32)),
    bone("chest", "spine_upper", [dims.torsoUpper, 0], 0, dims.chestLength, ["core"]),
    bone("neck", "chest", [dims.chestLength, 0], 0, dims.neckLength, ["core", "look_at"], jointLimit(-42, 42)),
    bone("head", "neck", [dims.neckLength, 0], 0, dims.headLength, ["core", "look_at"], jointLimit(-35, 35)),
    bone("eye_l", "head", [dims.headLength * 0.56, eyeY], 0, 0.04 * dims.heightScale, ["face", "l", "look_at"]),
    bone("eye_r", "head", [dims.headLength * 0.56, -eyeY], 0, 0.04 * dims.heightScale, ["face", "r", "look_at"])
  ];

  for (const side of ["l", "r"] as const) {
    const sign = side === "l" ? 1 : -1;
    const factor = sideFactor(side, dims.sideAsymmetry);
    bones.push(
      bone(`clavicle_${side}`, "chest", [dims.chestLength * 0.9, sign * shoulderY * 0.22], sign * 94, dims.clavicleLength, ["arm", side]),
      bone(`upper_arm_${side}`, `clavicle_${side}`, [dims.clavicleLength, 0], sign * 77, dims.upperArmLength * factor, ["arm", side, "ik_chain"], jointLimit(-170, 170)),
      bone(`forearm_${side}`, `upper_arm_${side}`, [dims.upperArmLength * factor, 0], -sign * 5, dims.forearmLength * factor, ["arm", side, "ik_chain"], side === "l" ? jointLimit(-150, 6) : jointLimit(-6, 150)),
      bone(`hand_${side}`, `forearm_${side}`, [dims.forearmLength * factor, 0], 0, dims.handLength * factor, ["arm", side], jointLimit(-55, 55)),
      bone(`thigh_${side}`, "hips", [-dims.hipLength * 0.22, sign * hipY * 0.43], 180, dims.thighLength * factor, ["leg", side, "ik_chain"], jointLimit(-120, 120)),
      bone(`shin_${side}`, `thigh_${side}`, [dims.thighLength * factor, 0], 0, dims.shinLength * factor, ["leg", side, "ik_chain"], side === "l" ? jointLimit(-6, 150) : jointLimit(-150, 6)),
      bone(`foot_${side}`, `shin_${side}`, [dims.shinLength * factor, 0], 90, dims.footLength * factor, ["leg", side], jointLimit(-55, 55)),
      bone(`toe_${side}`, `foot_${side}`, [dims.footLength * factor, 0], 0, dims.toeLength * factor, ["leg", side], jointLimit(-15, 35))
    );
  }

  return { id: `rig_proc_${stableSuffix(request)}`, name: "Procedural human rig", bones };
}

export function generateRigConstraints(rig: RigDefinition): GeneratedConstraintDefinition[] {
  const boneIds = new Set(rig.bones.map((boneItem) => boneItem.id));
  const constraints: GeneratedConstraintDefinition[] = [];
  for (const side of ["l", "r"] as const) {
    const armBones = [`upper_arm_${side}`, `forearm_${side}`, `hand_${side}`];
    const legBones = [`thigh_${side}`, `shin_${side}`, `foot_${side}`];
    if (armBones.every((boneId) => boneIds.has(boneId))) {
      constraints.push({
        id: `ik_arm_${side}`,
        type: "two_bone_ik",
        bone_ids: armBones,
        effector_bone_id: `hand_${side}`,
        tags: ["arm", side]
      });
    }
    if (legBones.every((boneId) => boneIds.has(boneId))) {
      constraints.push({
        id: `ik_leg_${side}`,
        type: "two_bone_ik",
        bone_ids: legBones,
        effector_bone_id: `foot_${side}`,
        tags: ["leg", side]
      });
    }
  }
  if (["neck", "head"].every((boneId) => boneIds.has(boneId))) {
    constraints.push({
      id: "look_head",
      type: "look_at",
      bone_ids: ["neck", "head"],
      effector_bone_id: "head",
      tags: ["look_at"]
    });
  }
  if (["eye_l", "eye_r"].every((boneId) => boneIds.has(boneId))) {
    constraints.push({
      id: "look_eyes",
      type: "look_at",
      bone_ids: ["eye_l", "eye_r"],
      effector_bone_id: "eye_l",
      tags: ["look_at", "face"]
    });
  }
  return constraints;
}

function styleFill(request: CharacterBuilderRequest, color: string): string {
  return request.style === "silhouette" ? "#222222" : color;
}

function styleOpacity(request: CharacterBuilderRequest, base = 1): number {
  return request.style === "paper_cutout" ? Math.min(base, 0.94) : base;
}

function primitive(options: {
  readonly id: string;
  readonly boneId: string;
  readonly shape: "capsule" | "ellipse" | "rectangle";
  readonly size: readonly [number, number];
  readonly fill: string;
  readonly position?: readonly [number, number];
  readonly zIndex?: number;
  readonly opacity?: number;
}): AttachmentDefinition {
  return {
    id: options.id,
    bone_id: options.boneId,
    kind: "primitive",
    asset_id: null,
    primitive: {
      shape: options.shape,
      size: [round6(options.size[0]), round6(options.size[1])],
      fill: options.fill,
      opacity: options.opacity ?? 1
    },
    mesh: null,
    pivot: [0, 0],
    transform: {
      position: options.position === undefined ? [0, 0] : [round6(options.position[0]), round6(options.position[1])],
      rotation_deg: 0,
      scale: [1, 1]
    },
    z_index: options.zIndex ?? 0,
    visible: true
  };
}

function matrixTuple(matrix: {
  readonly a: number;
  readonly b: number;
  readonly c: number;
  readonly d: number;
  readonly tx: number;
  readonly ty: number;
}): [number, number, number, number, number, number] {
  return [
    round6(matrix.a),
    round6(matrix.b),
    round6(matrix.c),
    round6(matrix.d),
    round6(matrix.tx),
    round6(matrix.ty)
  ];
}

function relativeBindPose(
  rig: RigDefinition,
  ownerBoneId: string,
  boneIds: readonly [string, string]
) {
  const worlds = computeWorldTransforms(rig);
  const owner = worlds.get(ownerBoneId);
  if (owner === undefined) {
    throw new Error(`owner bone '${ownerBoneId}' is missing`);
  }
  const ownerInverse = inverse(owner);
  return boneIds.map((boneId) => {
    const world = worlds.get(boneId);
    if (world === undefined) {
      throw new Error(`influence bone '${boneId}' is missing`);
    }
    const bind: Affine2 = multiply(ownerInverse, world);
    return {
      bone_id: boneId,
      bind_matrix: matrixTuple(bind),
      inverse_bind_matrix: matrixTuple(inverse(bind))
    };
  });
}

function meshAttachment(options: {
  readonly id: string;
  readonly ownerBoneId: string;
  readonly influenceBoneIds: readonly [string, string];
  readonly rig: RigDefinition;
  readonly lengthA: number;
  readonly lengthB: number;
  readonly width: number;
  readonly fill: string;
  readonly zIndex: number;
  readonly opacity?: number;
  readonly secondaryMotion?: number;
}): AttachmentDefinition {
  const seamX = round6(options.lengthA);
  const endX = round6(options.lengthA + options.lengthB);
  const half = round6(options.width / 2);
  const [first, second] = options.influenceBoneIds;
  return {
    id: options.id,
    bone_id: options.ownerBoneId,
    kind: "mesh",
    asset_id: null,
    primitive: null,
    mesh: {
      vertices: [
        [0, -half],
        [0, half],
        [seamX, -half],
        [seamX, half],
        [endX, -round6(half * 0.88)],
        [endX, round6(half * 0.88)]
      ],
      triangles: [
        { indices: [0, 2, 1] },
        { indices: [1, 2, 3] },
        { indices: [2, 4, 3] },
        { indices: [3, 4, 5] }
      ],
      weights: [
        { weights: [{ bone_id: first, weight: 1 }] },
        { weights: [{ bone_id: first, weight: 1 }] },
        { weights: [{ bone_id: first, weight: 0.5 }, { bone_id: second, weight: 0.5 }] },
        { weights: [{ bone_id: first, weight: 0.5 }, { bone_id: second, weight: 0.5 }] },
        { weights: [{ bone_id: second, weight: 1 }] },
        { weights: [{ bone_id: second, weight: 1 }] }
      ],
      bind_pose: relativeBindPose(options.rig, options.ownerBoneId, options.influenceBoneIds),
      fill: options.fill,
      opacity: options.opacity ?? 1,
      smoothing: 0.7,
      secondary_motion: options.secondaryMotion ?? 0
    },
    pivot: [0, 0],
    transform: { position: [0, 0], rotation_deg: 0, scale: [1, 1] },
    z_index: options.zIndex,
    visible: true
  };
}

function hairSizes(style: CharacterBuilderRequest["hair_style"], dims: HumanDimensions) {
  const back = { bald: 0, short: 0.34, bob: 0.46, curly: 0.46, long: 0.72, coily: 0.52 }[style];
  const front = { bald: 0, short: 0.18, bob: 0.22, curly: 0.26, long: 0.28, coily: 0.3 }[style];
  return {
    back: [Math.max(0.01, dims.headLength * back), dims.headWidth * 1.08] as const,
    front: [Math.max(0.01, dims.headLength * front), dims.headWidth * 0.96] as const
  };
}

export function generateVectorAttachments(
  request: CharacterBuilderRequest,
  rig: RigDefinition,
  region: CharacterBuilderRegion = "all"
): AttachmentDefinition[] {
  const dims = dimensions(request);
  const skin = styleFill(request, request.palette.skin);
  const hair = styleFill(request, request.palette.hair);
  const top = styleFill(request, request.palette.top);
  const bottom = styleFill(request, request.palette.bottom);
  const shoes = styleFill(request, request.palette.shoes);
  const accent = styleFill(request, request.palette.accent);
  const ink = request.style === "silhouette" ? "#222222" : "#1f2328";
  const attachments: AttachmentDefinition[] = [];

  if (region === "all") {
    attachments.push(
      primitive({ id: "part_neck", boneId: "neck", shape: "capsule", size: [dims.neckLength, dims.armThickness * 0.72], fill: skin }),
      primitive({ id: "part_torso", boneId: "chest", shape: "rectangle", size: [dims.chestLength * 1.05, dims.shoulderWidth], fill: top, zIndex: 4, opacity: styleOpacity(request, 0.96) }),
      primitive({ id: "part_waist", boneId: "spine_lower", shape: "rectangle", size: [dims.torsoLower + dims.torsoUpper * 0.4, dims.waistWidth], fill: top, zIndex: 3, opacity: styleOpacity(request, 0.94) }),
      primitive({ id: "part_pelvis", boneId: "hips", shape: "rectangle", size: [dims.hipLength * 1.08, dims.pelvisWidth], fill: bottom, zIndex: 2, opacity: styleOpacity(request, 0.96) }),
      primitive({ id: "part_head", boneId: "head", shape: "ellipse", size: [dims.headLength * 0.92, dims.headWidth], fill: skin, position: [dims.headLength * 0.02, 0], zIndex: 8 })
    );
    for (const side of ["l", "r"] as const) {
      const factor = sideFactor(side, dims.sideAsymmetry);
      const backZ = side === "r" ? -3 : 5;
      attachments.push(
        primitive({ id: `part_upper_arm_${side}`, boneId: `upper_arm_${side}`, shape: "capsule", size: [dims.upperArmLength * factor, dims.armThickness], fill: request.top === "shirt" ? skin : top, zIndex: backZ, opacity: styleOpacity(request) }),
        primitive({ id: `part_forearm_${side}`, boneId: `forearm_${side}`, shape: "capsule", size: [dims.forearmLength * factor, dims.armThickness * 0.88], fill: skin, zIndex: backZ }),
        primitive({ id: `part_hand_${side}`, boneId: `hand_${side}`, shape: "ellipse", size: [dims.handLength * factor, dims.armThickness * 1.02], fill: skin, zIndex: backZ + 1 }),
        primitive({ id: `part_thigh_${side}`, boneId: `thigh_${side}`, shape: "capsule", size: [dims.thighLength * factor, dims.legThickness], fill: bottom, zIndex: side === "r" ? -1 : 1, opacity: styleOpacity(request) }),
        primitive({ id: `part_shin_${side}`, boneId: `shin_${side}`, shape: "capsule", size: [dims.shinLength * factor, dims.legThickness * 0.86], fill: request.bottom === "shorts" ? skin : bottom, zIndex: side === "r" ? -1 : 1, opacity: styleOpacity(request) }),
        primitive({ id: `part_foot_${side}`, boneId: `foot_${side}`, shape: "capsule", size: [dims.footLength * factor, dims.legThickness * 0.72], fill: shoes, zIndex: 3 }),
        primitive({ id: `part_toe_${side}`, boneId: `toe_${side}`, shape: "capsule", size: [dims.toeLength * factor, dims.legThickness * 0.58], fill: shoes, zIndex: 3 })
      );
      if (request.top === "sweater" || request.top === "jacket") {
        attachments.push(
          meshAttachment({
            id: `mesh_sleeve_${side}`,
            ownerBoneId: `upper_arm_${side}`,
            influenceBoneIds: [`upper_arm_${side}`, `forearm_${side}`],
            rig,
            lengthA: dims.upperArmLength * factor,
            lengthB: dims.forearmLength * factor,
            width: dims.armThickness * (request.top === "jacket" ? 1.16 : 1.02),
            fill: top,
            zIndex: backZ + 2,
            opacity: styleOpacity(request, 0.9),
            secondaryMotion: request.top === "jacket" ? 0.18 : 0.08
          })
        );
      }
      if (request.bottom === "trousers") {
        attachments.push(
          meshAttachment({
            id: `mesh_trouser_${side}`,
            ownerBoneId: `thigh_${side}`,
            influenceBoneIds: [`thigh_${side}`, `shin_${side}`],
            rig,
            lengthA: dims.thighLength * factor,
            lengthB: dims.shinLength * factor,
            width: dims.legThickness * 1.04,
            fill: bottom,
            zIndex: side === "r" ? 0 : 2,
            opacity: styleOpacity(request, 0.88),
            secondaryMotion: 0.05
          })
        );
      }
    }
  }

  if ((region === "all" || region === "hair") && request.hair_style !== "bald") {
    const sizes = hairSizes(request.hair_style, dims);
    attachments.push(
      primitive({ id: "part_hair_back", boneId: "head", shape: "ellipse", size: sizes.back, fill: hair, position: [-dims.headLength * 0.08, 0], zIndex: 6, opacity: styleOpacity(request) }),
      primitive({ id: "part_hair_front", boneId: "head", shape: request.hair_style === "curly" || request.hair_style === "coily" ? "ellipse" : "rectangle", size: sizes.front, fill: hair, position: [dims.headLength * 0.45, 0], zIndex: 10, opacity: styleOpacity(request) })
    );
  }

  if (region === "all" || region === "face") {
    const eyeSize = dims.headWidth * 0.105;
    attachments.push(
      primitive({ id: "part_eye_l", boneId: "eye_l", shape: "ellipse", size: [eyeSize, eyeSize], fill: ink, zIndex: 12 }),
      primitive({ id: "part_eye_r", boneId: "eye_r", shape: "ellipse", size: [eyeSize, eyeSize], fill: ink, zIndex: 12 }),
      primitive({ id: "part_brow_l", boneId: "eye_l", shape: "rectangle", size: [eyeSize * 1.4, eyeSize * 0.28], fill: hair, position: [0, eyeSize * 1.15], zIndex: 13 }),
      primitive({ id: "part_brow_r", boneId: "eye_r", shape: "rectangle", size: [eyeSize * 1.4, eyeSize * 0.28], fill: hair, position: [0, eyeSize * 1.15], zIndex: 13 }),
      primitive({ id: "part_nose", boneId: "head", shape: "capsule", size: [dims.headLength * 0.12, eyeSize * 0.8], fill: request.style === "silhouette" ? ink : "#8b5e42", position: [dims.headLength * 0.58, 0], zIndex: 13, opacity: 0.8 }),
      primitive({ id: "part_mouth", boneId: "head", shape: "rectangle", size: [dims.headLength * 0.14, eyeSize * 0.25], fill: request.style === "silhouette" ? ink : "#8b1e32", position: [dims.headLength * 0.72, 0], zIndex: 13 })
    );
  }

  if (region === "all" || region === "clothing") {
    if (request.outerwear !== "none") {
      attachments.push(
        primitive({ id: "part_outerwear", boneId: "chest", shape: "rectangle", size: [dims.chestLength * (request.outerwear === "coat" ? 1.12 : 0.98), dims.shoulderWidth * 1.08], fill: accent, zIndex: 7, opacity: styleOpacity(request, 0.78) })
      );
      for (const side of ["l", "r"] as const) {
        const factor = sideFactor(side, dims.sideAsymmetry);
        attachments.push(
          meshAttachment({
            id: `mesh_outer_sleeve_${side}`,
            ownerBoneId: `upper_arm_${side}`,
            influenceBoneIds: [`upper_arm_${side}`, `forearm_${side}`],
            rig,
            lengthA: dims.upperArmLength * factor,
            lengthB: dims.forearmLength * factor,
            width: dims.armThickness * 1.32,
            fill: accent,
            zIndex: 8,
            opacity: styleOpacity(request, 0.72),
            secondaryMotion: request.outerwear === "coat" ? 0.22 : 0.12
          })
        );
      }
    }
    if (request.bottom === "skirt") {
      attachments.push(
        primitive({ id: "part_skirt", boneId: "hips", shape: "rectangle", size: [dims.hipLength * 1.42, dims.pelvisWidth * 1.22], fill: bottom, zIndex: 6, opacity: styleOpacity(request, 0.94) })
      );
      attachments.push(
        meshAttachment({
          id: "mesh_skirt_panel",
          ownerBoneId: "hips",
          influenceBoneIds: ["hips", "spine_lower"],
          rig,
          lengthA: dims.hipLength * 0.82,
          lengthB: dims.torsoLower * 0.42,
          width: dims.pelvisWidth * 1.28,
          fill: bottom,
          zIndex: 7,
          opacity: styleOpacity(request, 0.72),
          secondaryMotion: 0.35
        })
      );
    }
    if (request.footwear === "boots" || request.footwear === "sneakers") {
      for (const side of ["l", "r"] as const) {
        const factor = sideFactor(side, dims.sideAsymmetry);
        attachments.push(
          primitive({ id: `part_${request.footwear}_${side}`, boneId: `foot_${side}`, shape: request.footwear === "boots" ? "rectangle" : "capsule", size: [dims.footLength * factor * 0.82, dims.legThickness * 0.84], fill: request.footwear === "sneakers" ? accent : shoes, zIndex: 4 })
        );
      }
    }
  }

  return attachments;
}

function characterDiagnostics(character: CharacterDefinition): BuilderDiagnostic[] {
  const diagnostics: BuilderDiagnostic[] = [];
  const boneIds = new Set(character.rig.bones.map((boneItem) => boneItem.id));
  for (const boneItem of character.rig.bones) {
    if (boneItem.id !== "root" && boneItem.length <= 0) {
      diagnostics.push({
        code: "BUILDER_ZERO_BONE_LENGTH",
        severity: "error",
        message: `${boneItem.id} has a non-positive length`,
        path: `rig.bones.${boneItem.id}.length`
      });
    }
  }
  for (const attachment of character.attachments) {
    if (!boneIds.has(attachment.bone_id)) {
      diagnostics.push({
        code: "CHAR_ATTACHMENT_UNKNOWN_BONE",
        severity: "error",
        message: `${attachment.id} references an unknown bone`,
        path: `attachments.${attachment.id}.bone_id`
      });
    }
    if (attachment.kind === "primitive" && (attachment.primitive === null || attachment.primitive.size.some((value) => value <= 0))) {
      diagnostics.push({
        code: "BUILDER_NONPOSITIVE_PART_DIMENSION",
        severity: "error",
        message: `${attachment.id} has a non-positive primitive size`,
        path: `attachments.${attachment.id}.primitive.size`
      });
    }
    if (attachment.kind === "mesh" && attachment.mesh !== null) {
      for (const [vertexIndex, vertexWeights] of attachment.mesh.weights.entries()) {
        const total = vertexWeights.weights.reduce((sum, weight) => sum + weight.weight, 0);
        if (Math.abs(total - 1) > 1e-6) {
          diagnostics.push({
            code: "BUILDER_MESH_WEIGHT_SUM",
            severity: "error",
            message: `${attachment.id} vertex ${vertexIndex} weights do not sum to 1`,
            path: `attachments.${attachment.id}.mesh.weights.${vertexIndex}`
          });
        }
      }
    }
  }
  return diagnostics;
}

export function buildProceduralCharacter(
  input: CharacterBuilderRequest
): CharacterBuilderResult {
  const parsed = characterBuilderRequestSchema.parse(input);
  const normalized = normalizeCharacterBuilderRequest(parsed);
  const suffix = stableSuffix(normalized.request);
  const rig = generateCanonicalHumanRig(normalized.request);
  const character: CharacterDefinition = {
    id: `char_proc_${suffix}`,
    name: normalized.request.name,
    rig,
    attachments: generateVectorAttachments(normalized.request, rig)
  };
  return {
    generatorVersion: GENERATOR_VERSION,
    normalizedRequest: normalized.request,
    character,
    constraints: generateRigConstraints(rig),
    diagnostics: [...normalized.diagnostics, ...characterDiagnostics(character)]
  };
}

const REGION_PREFIXES: Record<Exclude<CharacterBuilderRegion, "all">, readonly string[]> = {
  hair: ["part_hair_"],
  face: ["part_eye_", "part_brow_", "part_nose", "part_mouth"],
  clothing: [
    "part_torso",
    "part_waist",
    "part_pelvis",
    "part_upper_arm_",
    "part_thigh_",
    "part_shin_",
    "part_foot_",
    "part_toe_",
    "part_outerwear",
    "part_skirt",
    "part_boots_",
    "part_sneakers_"
  ]
};

function attachmentInRegion(attachment: AttachmentDefinition, region: CharacterBuilderRegion) {
  return region !== "all" && REGION_PREFIXES[region].some((prefix) => attachment.id.startsWith(prefix));
}

export function regenerateCharacterRegion(
  request: CharacterBuilderRequest,
  current: CharacterDefinition,
  region: CharacterBuilderRegion
): CharacterDefinition {
  if (region === "all") {
    return buildProceduralCharacter(request).character;
  }
  const normalized = normalizeCharacterBuilderRequest(characterBuilderRequestSchema.parse(request)).request;
  const generatedParts = generateVectorAttachments(normalized, current.rig, region);
  return {
    ...current,
    attachments: [
      ...current.attachments.filter((attachment) => !attachmentInRegion(attachment, region)),
      ...generatedParts
    ].sort((a, b) => a.z_index - b.z_index || a.id.localeCompare(b.id))
  };
}

export function createGeneratedCharacterProjectDocument(
  character: CharacterDefinition,
  uniqueToken: string
): ProjectDocument {
  const safeToken = uniqueToken.toLowerCase().replace(/[^a-z0-9_-]+/g, "_").replace(/^_+/, "");
  const suffix = safeToken || Date.now().toString(36);
  return projectDocumentSchema.parse({
    asset_manifest: [],
    characters: [character],
    clips: [],
    engine_version: "0.1.0",
    format: "rigstory-project",
    generation_records: [],
    motion_plans: [],
    project: {
      id: `project_builder_${suffix}`,
      name: `${character.name} Character`
    },
    scenes: [],
    schema_version: PROJECT_SCHEMA_VERSION
  });
}
