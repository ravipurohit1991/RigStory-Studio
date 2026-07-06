/**
 * Zod schemas for imported project files.
 *
 * These mirror the backend Pydantic domain models (backend/app/domain) and
 * exist to validate untrusted files at the import boundary. Shared samples
 * under samples/ are validated by both sides in CI, which keeps the two
 * schema sets in agreement. The generated OpenAPI client covers API traffic;
 * this layer covers files.
 */

import { z } from "zod";

export const PROJECT_SCHEMA_VERSION = "0.6.0";
export const MAX_ACTORS_PER_SCENE = 2;

const SLUG = /^[a-z][a-z0-9_]*$/;
const NAMESPACED_SLUG = /^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$/;
const SEMVER = /^\d+\.\d+\.\d+$/;

const prefixedId = (prefix: string) => z.string().regex(new RegExp(`^${prefix}_[a-z0-9][a-z0-9_-]*$`));

const point2 = z.tuple([z.number(), z.number()]);
const bounds4 = z.tuple([z.number(), z.number(), z.number(), z.number()]);
const matrix2d = z.tuple([z.number(), z.number(), z.number(), z.number(), z.number(), z.number()]);
const hexColor = z.string().regex(/^#[0-9a-fA-F]{6}$/);

export const transformSpecSchema = z.strictObject({
  position: point2.default([0, 0]),
  rotation_deg: z.number().default(0),
  scale: z
    .tuple([z.number(), z.number()])
    .default([1, 1])
    .refine(([sx, sy]) => sx !== 0 && sy !== 0, "scale components must be non-zero")
});

export const jointLimitSchema = z
  .strictObject({
    min_rotation_deg: z.number(),
    max_rotation_deg: z.number(),
    soft_zone_deg: z.number().min(0).default(0)
  })
  .refine(
    (limit) => limit.min_rotation_deg <= limit.max_rotation_deg,
    "joint limit is inverted: min exceeds max"
  );

export const boneSchema = z.strictObject({
  id: z.string().regex(NAMESPACED_SLUG),
  parent_id: z.string().regex(NAMESPACED_SLUG).nullable().default(null),
  setup_transform: transformSpecSchema.default({
    position: [0, 0],
    rotation_deg: 0,
    scale: [1, 1]
  }),
  length: z.number().min(0),
  joint_limit: jointLimitSchema.nullable().default(null),
  tags: z.array(z.string()).default([])
});

export const rigSchema = z.strictObject({
  id: prefixedId("rig"),
  name: z.string().min(1),
  bones: z.array(boneSchema)
});

export const primitiveAttachmentSchema = z.strictObject({
  shape: z.enum(["capsule", "ellipse", "rectangle"]).default("capsule"),
  size: point2.default([0.4, 0.16]),
  fill: hexColor.default("#e6b17a"),
  opacity: z.number().min(0).max(1).default(1)
});

export const meshVertexWeightSchema = z.strictObject({
  bone_id: z.string().regex(NAMESPACED_SLUG),
  weight: z.number().min(0).max(1)
});

export const meshVertexWeightsSchema = z
  .strictObject({
    weights: z.array(meshVertexWeightSchema).min(1)
  })
  .refine(
    (value) => Math.abs(value.weights.reduce((sum, weight) => sum + weight.weight, 0) - 1) <= 1e-6,
    "mesh vertex weights must sum to 1.0"
  )
  .refine(
    (value) => new Set(value.weights.map((weight) => weight.bone_id)).size === value.weights.length,
    "mesh vertex weights must not repeat a bone_id"
  );

export const meshTriangleSchema = z
  .strictObject({
    indices: z.tuple([z.number().int().min(0), z.number().int().min(0), z.number().int().min(0)])
  })
  .refine((triangle) => new Set(triangle.indices).size === 3, "mesh triangle indices must be distinct");

export const meshBindPoseSchema = z.strictObject({
  bone_id: z.string().regex(NAMESPACED_SLUG),
  bind_matrix: matrix2d,
  inverse_bind_matrix: matrix2d
});

export const meshAttachmentSchema = z
  .strictObject({
    vertices: z.array(point2).min(3),
    triangles: z.array(meshTriangleSchema).min(1),
    weights: z.array(meshVertexWeightsSchema).min(3),
    bind_pose: z.array(meshBindPoseSchema).min(1),
    fill: hexColor.default("#e6b17a"),
    opacity: z.number().min(0).max(1).default(1),
    smoothing: z.number().min(0).max(1).default(0),
    secondary_motion: z.number().min(0).max(1).default(0)
  })
  .refine((mesh) => mesh.weights.length === mesh.vertices.length, "mesh weights length must match vertices length")
  .refine(
    (mesh) => mesh.triangles.every((triangle) => triangle.indices.every((index) => index < mesh.vertices.length)),
    "mesh triangle index exceeds vertex count"
  )
  .refine(
    (mesh) => new Set(mesh.bind_pose.map((bind) => bind.bone_id)).size === mesh.bind_pose.length,
    "mesh bind pose must not repeat a bone_id"
  );

export const attachmentSchema = z.strictObject({
  id: z.string().regex(NAMESPACED_SLUG),
  bone_id: z.string().regex(NAMESPACED_SLUG),
  kind: z.enum(["primitive", "svg", "png", "mesh"]),
  asset_id: prefixedId("asset").nullable().default(null),
  primitive: primitiveAttachmentSchema.nullable().default(null),
  mesh: meshAttachmentSchema.nullable().default(null),
  pivot: point2.default([0, 0]),
  transform: transformSpecSchema.default({ position: [0, 0], rotation_deg: 0, scale: [1, 1] }),
  z_index: z.number().int().default(0),
  visible: z.boolean().default(true)
}).superRefine((attachment, ctx) => {
  if (attachment.kind === "mesh" && attachment.mesh === null) {
    ctx.addIssue({ code: "custom", message: "mesh attachments require a mesh payload", path: ["mesh"] });
  }
  if (attachment.kind !== "mesh" && attachment.mesh !== null) {
    ctx.addIssue({ code: "custom", message: "only mesh attachments may include a mesh payload", path: ["mesh"] });
  }
});

export const characterSchema = z.strictObject({
  id: prefixedId("char"),
  name: z.string().min(1),
  rig: rigSchema,
  attachments: z.array(attachmentSchema).default([])
});

const boxColliderSchema = z.strictObject({
  type: z.literal("box"),
  center: point2.default([0, 0]),
  size: point2,
  rotation_deg: z.number().default(0)
});

const circleColliderSchema = z.strictObject({
  type: z.literal("circle"),
  center: point2.default([0, 0]),
  radius: z.number().positive()
});

const capsuleColliderSchema = z.strictObject({
  type: z.literal("capsule"),
  point_a: point2,
  point_b: point2,
  radius: z.number().positive()
});

const polygonColliderSchema = z.strictObject({
  type: z.literal("polygon"),
  vertices: z.array(point2).min(3)
});

export const colliderSchema = z.discriminatedUnion("type", [
  boxColliderSchema,
  circleColliderSchema,
  capsuleColliderSchema,
  polygonColliderSchema
]);

const rectangleVisualSchema = z.strictObject({
  type: z.literal("rectangle"),
  fill: hexColor.default("#d8dee9"),
  opacity: z.number().min(0).max(1).default(1)
});

const polygonVisualSchema = z.strictObject({
  type: z.literal("polygon"),
  vertices: z.array(point2).min(3),
  fill: hexColor.default("#d8dee9"),
  opacity: z.number().min(0).max(1).default(1)
});

const assetVisualSchema = z.strictObject({
  type: z.enum(["svg", "png"]),
  asset_id: prefixedId("asset"),
  opacity: z.number().min(0).max(1).default(1)
});

export const objectVisualSchema = z.discriminatedUnion("type", [
  rectangleVisualSchema,
  polygonVisualSchema,
  assetVisualSchema
]);

export const anchorSchema = z.strictObject({
  id: z.string().regex(SLUG),
  position: point2,
  rotation_deg: z.number().default(0)
});

export const affordanceSchema = z.strictObject({
  type: z.enum(["sit", "stand_on", "grasp", "lean", "look_at", "avoid"]),
  anchor_id: z.string().regex(SLUG).nullable().default(null)
});

export const sceneObjectSchema = z.strictObject({
  id: z.string().regex(SLUG),
  name: z.string().min(1),
  kind: z.string().min(1),
  transform: transformSpecSchema.default({ position: [0, 0], rotation_deg: 0, scale: [1, 1] }),
  bounds: bounds4,
  visual: objectVisualSchema.default({ type: "rectangle", fill: "#d8dee9", opacity: 1 }),
  colliders: z.array(colliderSchema).default([]),
  anchors: z.array(anchorSchema).default([]),
  affordances: z.array(affordanceSchema).default([]),
  collision_layer: z.string().default("default"),
  collision_mask: z.array(z.string()).default(["default"]),
  body_type: z.enum(["static", "kinematic", "decorative"]).default("static"),
  visible: z.boolean().default(true),
  locked: z.boolean().default(false),
  walkable: z.boolean().default(false),
  blocked: z.boolean().default(false)
});

export const actorSchema = z.strictObject({
  id: prefixedId("actor"),
  character_id: prefixedId("char"),
  display_name: z.string().min(1),
  root_transform: transformSpecSchema.default({ position: [0, 0], rotation_deg: 0, scale: [1, 1] }),
  facing: z.enum(["left", "right"]).default("right"),
  state: z.string().regex(SLUG).default("standing")
});

export const sceneSchema = z.strictObject({
  id: prefixedId("scene"),
  name: z.string().min(1),
  world_bounds: bounds4,
  ground_y: z.number().default(0),
  actors: z.array(actorSchema).max(MAX_ACTORS_PER_SCENE).default([]),
  objects: z.array(sceneObjectSchema).default([])
});

const interpolationSchema = z.enum(["stepped", "linear", "cubic"]);

const scalarKeyframeSchema = z.strictObject({
  id: prefixedId("key"),
  time: z.number().min(0),
  value: z.number(),
  interpolation: interpolationSchema.default("linear")
});

const vectorKeyframeSchema = z.strictObject({
  id: prefixedId("key"),
  time: z.number().min(0),
  value: point2,
  interpolation: interpolationSchema.default("linear")
});

const boneRotationTrackSchema = z.strictObject({
  type: z.literal("bone_rotation"),
  id: prefixedId("track"),
  actor_id: prefixedId("actor"),
  bone_id: z.string().regex(NAMESPACED_SLUG),
  keyframes: z.array(scalarKeyframeSchema).default([])
});

const rootTranslationTrackSchema = z.strictObject({
  type: z.literal("root_translation"),
  id: prefixedId("track"),
  actor_id: prefixedId("actor"),
  keyframes: z.array(vectorKeyframeSchema).default([])
});

const boneScaleTrackSchema = z.strictObject({
  type: z.literal("bone_scale"),
  id: prefixedId("track"),
  actor_id: prefixedId("actor"),
  bone_id: z.string().regex(NAMESPACED_SLUG),
  keyframes: z.array(vectorKeyframeSchema).default([])
});

const constraintWeightTrackSchema = z.strictObject({
  type: z.literal("constraint_weight"),
  id: prefixedId("track"),
  actor_id: prefixedId("actor"),
  constraint_id: z.string().regex(SLUG),
  keyframes: z.array(scalarKeyframeSchema).default([])
});

export const trackSchema = z.discriminatedUnion("type", [
  boneRotationTrackSchema,
  rootTranslationTrackSchema,
  boneScaleTrackSchema,
  constraintWeightTrackSchema
]);

const clipEventSchema = z.strictObject({
  name: z.string().regex(SLUG),
  time: z.number().min(0),
  params: z.record(z.string(), z.union([z.string(), z.number(), z.boolean()])).default({})
});

const clipMarkerSchema = z.strictObject({
  name: z.string().min(1),
  time: z.number().min(0),
  kind: z.enum(["marker", "contact", "sync"]).default("marker")
});

export const clipSchema = z.strictObject({
  id: prefixedId("clip"),
  scene_id: prefixedId("scene"),
  name: z.string().min(1),
  duration: z.number().positive(),
  loop: z.boolean().default(false),
  loop_range: point2.nullable().default(null),
  tracks: z.array(trackSchema).default([]),
  events: z.array(clipEventSchema).default([]),
  markers: z.array(clipMarkerSchema).default([]),
  // Present when the clip was compiled from a motion plan (schema 0.5.0).
  source_plan_id: prefixedId("plan").nullable().default(null),
  engine_version: z.string().nullable().default(null)
});

// Motion plans (schema 0.5.0). Actions are validated structurally: the
// discriminated per-type parameter sets are enforced by the backend before a
// plan is ever persisted, so this import layer guards ids, ordering, and the
// supported action vocabulary.
const plannedActionSchema = z
  .looseObject({
    id: z.string().regex(SLUG),
    actor_id: prefixedId("actor"),
    type: z.enum([
      "idle",
      "shift_weight",
      "locomote",
      "approach",
      "retreat",
      "turn",
      "look_at",
      "reach",
      "point",
      "grasp",
      "release",
      "wave",
      "sit",
      "rise",
      "crouch",
      "kneel",
      "lean",
      "handshake"
    ]),
    starts_after: z.array(z.string().regex(SLUG)).default([]),
    duration: z.number().positive()
  });

const syncConstraintSchema = z.strictObject({
  kind: z.enum(["start_together", "finish_together", "meet_at_contact"]),
  action_ids: z.array(z.string().regex(SLUG)).min(2).max(4),
  contact_id: z.string().regex(SLUG).nullable().default(null)
});

const contactDefinitionSchema = z.strictObject({
  id: z.string().regex(SLUG),
  kind: z.enum(["hand_to_hand", "hand_to_object"]),
  reference_actor_id: prefixedId("actor"),
  reference_hand: z.enum(["left", "right"]).default("right"),
  follower_actor_id: prefixedId("actor").nullable().default(null),
  follower_hand: z.enum(["left", "right"]).nullable().default(null),
  target_ref: z.string().nullable().default(null),
  position_tolerance: z.number().positive().default(0.05),
  orientation_tolerance_deg: z.number().positive().default(15)
});

const planWarningSchema = z.strictObject({
  code: z.string().min(1),
  message: z.string().min(1),
  action_id: z.string().regex(SLUG).nullable().default(null)
});

const motionStyleSchema = z.strictObject({
  energy: z.number().min(0).max(1).default(0.35),
  tempo: z.number().positive().max(3).default(1),
  confidence: z.number().min(0).max(1).default(0.65),
  exaggeration: z.number().min(0).max(1).default(0.2),
  tension: z.number().min(0).max(1).default(0.2)
});

export const motionPlanSchema = z.strictObject({
  schema_version: z.string().regex(SEMVER),
  id: prefixedId("plan"),
  scene_id: prefixedId("scene"),
  prompt: z.string().default(""),
  created_at: z.string().default(""),
  summary: z.string().min(1),
  actions: z.array(plannedActionSchema).min(1).max(24),
  sync: z.array(syncConstraintSchema).default([]),
  contacts: z.array(contactDefinitionSchema).default([]),
  style: motionStyleSchema.default({
    energy: 0.35,
    tempo: 1,
    confidence: 0.65,
    exaggeration: 0.2,
    tension: 0.2
  }),
  warnings: z.array(planWarningSchema).default([])
});

const assetManifestEntrySchema = z.strictObject({
  id: prefixedId("asset"),
  sha256: z.string().regex(/^[0-9a-f]{64}$/),
  media_type: z.string().min(1),
  display_name: z.string().default("")
});

// Generation records (schema 0.3.0). The embedded blueprint and diagnostics are
// accepted permissively: this import layer guards structure, and the blueprint is
// re-validated by the backend before it ever produces a rig.
const generationAttemptSchema = z.strictObject({
  index: z.number().int().min(0),
  kind: z.enum(["initial", "repair"]),
  valid: z.boolean(),
  error_summary: z.array(z.string()).default([]),
  raw_response: z.string().default("")
});

const generationOptionsRecordSchema = z.looseObject({
  temperature: z.number(),
  keep_alive: z.string().nullable().default(null),
  timeout_seconds: z.number(),
  num_ctx: z.number().nullable().default(null)
});

const generationTimingSchema = z.looseObject({}).nullable();

export const generationRecordSchema = z.looseObject({
  id: prefixedId("gen"),
  kind: z
    .enum(["character_blueprint", "motion_plan", "motion_plan_patch"])
    .default("character_blueprint"),
  created_at: z.string().min(1),
  character_id: prefixedId("char").nullable().default(null),
  plan_id: prefixedId("plan").nullable().default(null),
  model_name: z.string().min(1),
  prompt_ids: z.array(z.string()).default([]),
  options: generationOptionsRecordSchema,
  status: z.enum(["succeeded", "repaired", "failed"]),
  failure_kind: z
    .enum(["none", "timeout", "invalid_response", "provider_error"])
    .default("none"),
  retryable: z.boolean().default(false),
  outcome_detail: z.string().default(""),
  attempts: z.array(generationAttemptSchema).default([]),
  timing: generationTimingSchema.default(null),
  blueprint: z.looseObject({}).nullable().default(null),
  builder_diagnostics: z.array(z.looseObject({})).default([]),
  warnings: z.array(z.string()).default([])
});

export const projectDocumentSchema = z.strictObject({
  format: z.literal("rigstory-project"),
  schema_version: z
    .string()
    .regex(SEMVER)
    .refine(
      (version) => version === PROJECT_SCHEMA_VERSION,
      `only schema_version ${PROJECT_SCHEMA_VERSION} is supported by the import layer`
    ),
  engine_version: z.string().regex(SEMVER),
  project: z.strictObject({
    id: prefixedId("project"),
    name: z.string().min(1)
  }),
  characters: z.array(characterSchema).default([]),
  scenes: z.array(sceneSchema).default([]),
  clips: z.array(clipSchema).default([]),
  motion_plans: z.array(motionPlanSchema).default([]),
  generation_records: z.array(generationRecordSchema).default([]),
  asset_manifest: z.array(assetManifestEntrySchema).default([])
});

export type TransformSpec = z.infer<typeof transformSpecSchema>;
export type BoneDefinition = z.infer<typeof boneSchema>;
export type RigDefinition = z.infer<typeof rigSchema>;
export type PrimitiveAttachment = z.infer<typeof primitiveAttachmentSchema>;
export type MeshAttachment = z.infer<typeof meshAttachmentSchema>;
export type AttachmentDefinition = z.infer<typeof attachmentSchema>;
export type CharacterDefinition = z.infer<typeof characterSchema>;
export type SceneDefinition = z.infer<typeof sceneSchema>;
export type AnimationClip = z.infer<typeof clipSchema>;
export type MotionPlan = z.infer<typeof motionPlanSchema>;
export type GenerationRecord = z.infer<typeof generationRecordSchema>;
export type ProjectDocument = z.infer<typeof projectDocumentSchema>;
