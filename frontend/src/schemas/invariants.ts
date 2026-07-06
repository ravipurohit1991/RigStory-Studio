/**
 * Cross-object invariants for imported project files, mirroring the backend
 * `validate_*` functions with the same error codes. Shape validation lives
 * in the Zod schemas; these checks cover reference integrity.
 */

import { validateRig, type ValidationIssue } from "../engine/rig";
import type { AnimationClip, ProjectDocument, SceneDefinition } from "./project";

export type { ValidationIssue };

const ANCHOR_REQUIRED_AFFORDANCES = new Set(["sit", "stand_on", "grasp", "lean"]);

export function validateScene(scene: SceneDefinition, pathPrefix = ""): ValidationIssue[] {
  const prefix = pathPrefix ? `${pathPrefix}.` : "";
  const issues: ValidationIssue[] = [];

  const [minX, minY, maxX, maxY] = scene.world_bounds;
  if (minX > maxX || minY > maxY) {
    issues.push({
      code: "SCENE_INVALID_BOUNDS",
      message: `world bounds min exceeds max: ${scene.world_bounds.join(", ")}`,
      path: `${prefix}world_bounds`
    });
  }

  const actorIds = new Set<string>();
  scene.actors.forEach((actor, index) => {
    if (actorIds.has(actor.id)) {
      issues.push({
        code: "SCENE_DUPLICATE_ACTOR_ID",
        message: `actor id '${actor.id}' is defined more than once`,
        path: `${prefix}actors[${index}].id`
      });
    }
    actorIds.add(actor.id);
  });

  const objectIds = new Set<string>();
  scene.objects.forEach((sceneObject, objectIndex) => {
    const objectPath = `${prefix}objects[${objectIndex}]`;
    if (objectIds.has(sceneObject.id)) {
      issues.push({
        code: "SCENE_DUPLICATE_OBJECT_ID",
        message: `object id '${sceneObject.id}' is defined more than once`,
        path: `${objectPath}.id`
      });
    }
    objectIds.add(sceneObject.id);

    const anchorIds = new Set(sceneObject.anchors.map((anchor) => anchor.id));
    sceneObject.affordances.forEach((affordance, affordanceIndex) => {
      const affordancePath = `${objectPath}.affordances[${affordanceIndex}]`;
      if (ANCHOR_REQUIRED_AFFORDANCES.has(affordance.type) && affordance.anchor_id === null) {
        issues.push({
          code: "SCENE_AFFORDANCE_MISSING_ANCHOR",
          message: `affordance '${affordance.type}' on object '${sceneObject.id}' requires an anchor_id`,
          path: `${affordancePath}.anchor_id`
        });
      } else if (affordance.anchor_id !== null && !anchorIds.has(affordance.anchor_id)) {
        issues.push({
          code: "SCENE_AFFORDANCE_UNKNOWN_ANCHOR",
          message: `affordance '${affordance.type}' on object '${sceneObject.id}' references unknown anchor '${affordance.anchor_id}'`,
          path: `${affordancePath}.anchor_id`
        });
      }
    });
  });

  return issues;
}

export function validateClip(clip: AnimationClip, pathPrefix = ""): ValidationIssue[] {
  const prefix = pathPrefix ? `${pathPrefix}.` : "";
  const issues: ValidationIssue[] = [];

  if (clip.loop_range !== null) {
    const [start, end] = clip.loop_range;
    if (start < 0 || end < 0 || start >= end || end > clip.duration) {
      issues.push({
        code: "CLIP_LOOP_RANGE_INVALID",
        message: "loop_range must be [start, end] with 0 <= start < end <= duration",
        path: `${prefix}loop_range`
      });
    }
  }

  const trackIds = new Set<string>();
  clip.tracks.forEach((track, trackIndex) => {
    const trackPath = `${prefix}tracks[${trackIndex}]`;
    if (trackIds.has(track.id)) {
      issues.push({
        code: "CLIP_DUPLICATE_TRACK_ID",
        message: `track id '${track.id}' is defined more than once`,
        path: `${trackPath}.id`
      });
    }
    trackIds.add(track.id);

    const keyframeIds = new Set<string>();
    let previousTime: number | null = null;
    track.keyframes.forEach((keyframe, keyIndex) => {
      const keyPath = `${trackPath}.keyframes[${keyIndex}]`;
      if (keyframeIds.has(keyframe.id)) {
        issues.push({
          code: "CLIP_DUPLICATE_KEYFRAME_ID",
          message: `keyframe id '${keyframe.id}' appears twice in track '${track.id}'`,
          path: `${keyPath}.id`
        });
      }
      keyframeIds.add(keyframe.id);
      if (previousTime !== null && keyframe.time <= previousTime) {
        issues.push({
          code: "CLIP_KEYFRAME_ORDER",
          message: `keyframe times must strictly increase in track '${track.id}'`,
          path: `${keyPath}.time`
        });
      }
      previousTime = keyframe.time;
      if (keyframe.time > clip.duration) {
        issues.push({
          code: "CLIP_KEYFRAME_OUT_OF_RANGE",
          message: `keyframe at ${keyframe.time}s exceeds clip duration ${clip.duration}s`,
          path: `${keyPath}.time`
        });
      }
    });
  });

  return issues;
}

export function validateProjectDocument(document: ProjectDocument): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  const characterIds = new Set<string>();
  document.characters.forEach((character, index) => {
    if (characterIds.has(character.id)) {
      issues.push({
        code: "PROJECT_DUPLICATE_ID",
        message: `character id '${character.id}' is defined more than once`,
        path: `characters[${index}].id`
      });
    }
    characterIds.add(character.id);
    issues.push(...validateRig(character.rig, `characters[${index}].rig`));

    const boneIds = new Set(character.rig.bones.map((bone) => bone.id));
    character.attachments.forEach((attachment, attachmentIndex) => {
      const attachmentPath = `characters[${index}].attachments[${attachmentIndex}]`;
      if (!boneIds.has(attachment.bone_id)) {
        issues.push({
          code: "CHAR_ATTACHMENT_UNKNOWN_BONE",
          message: `attachment '${attachment.id}' references unknown bone '${attachment.bone_id}'`,
          path: `${attachmentPath}.bone_id`
        });
      }
      if ((attachment.kind === "svg" || attachment.kind === "png") && attachment.asset_id === null) {
        issues.push({
          code: "CHAR_ATTACHMENT_ASSET_MISSING",
          message: `attachment '${attachment.id}' of kind '${attachment.kind}' requires an asset_id`,
          path: `${attachmentPath}.asset_id`
        });
      }
      if (attachment.kind === "mesh" && attachment.mesh !== null) {
        const bindBoneIds = new Set(attachment.mesh.bind_pose.map((bind) => bind.bone_id));
        attachment.mesh.bind_pose.forEach((bind, bindIndex) => {
          if (!boneIds.has(bind.bone_id)) {
            issues.push({
              code: "CHAR_MESH_UNKNOWN_BONE",
              message: `mesh attachment '${attachment.id}' bind pose references unknown bone '${bind.bone_id}'`,
              path: `${attachmentPath}.mesh.bind_pose[${bindIndex}].bone_id`
            });
          }
        });
        attachment.mesh.weights.forEach((vertexWeights, vertexIndex) => {
          vertexWeights.weights.forEach((weight, weightIndex) => {
            if (!boneIds.has(weight.bone_id)) {
              issues.push({
                code: "CHAR_MESH_UNKNOWN_BONE",
                message: `mesh attachment '${attachment.id}' vertex ${vertexIndex} references unknown bone '${weight.bone_id}'`,
                path: `${attachmentPath}.mesh.weights[${vertexIndex}].weights[${weightIndex}].bone_id`
              });
            }
            if (!bindBoneIds.has(weight.bone_id)) {
              issues.push({
                code: "CHAR_MESH_MISSING_BIND_POSE",
                message: `mesh attachment '${attachment.id}' vertex ${vertexIndex} references bone '${weight.bone_id}' without a bind pose`,
                path: `${attachmentPath}.mesh.weights[${vertexIndex}].weights[${weightIndex}].bone_id`
              });
            }
          });
        });
      }
    });
  });

  const actorsByScene = new Map<string, Map<string, string>>();
  const sceneIds = new Set<string>();
  document.scenes.forEach((scene, index) => {
    if (sceneIds.has(scene.id)) {
      issues.push({
        code: "PROJECT_DUPLICATE_ID",
        message: `scene id '${scene.id}' is defined more than once`,
        path: `scenes[${index}].id`
      });
    }
    sceneIds.add(scene.id);
    issues.push(...validateScene(scene, `scenes[${index}]`));

    const actorMap = new Map<string, string>();
    scene.actors.forEach((actor, actorIndex) => {
      actorMap.set(actor.id, actor.character_id);
      if (!characterIds.has(actor.character_id)) {
        issues.push({
          code: "SCENE_UNKNOWN_CHARACTER",
          message: `actor '${actor.id}' references unknown character '${actor.character_id}'`,
          path: `scenes[${index}].actors[${actorIndex}].character_id`
        });
      }
    });
    actorsByScene.set(scene.id, actorMap);
  });

  const charactersById = new Map(document.characters.map((character) => [character.id, character]));
  document.clips.forEach((clip, index) => {
    const clipPath = `clips[${index}]`;
    issues.push(...validateClip(clip, clipPath));

    const sceneActors = actorsByScene.get(clip.scene_id);
    if (sceneActors === undefined) {
      issues.push({
        code: "CLIP_UNKNOWN_SCENE",
        message: `clip '${clip.id}' references unknown scene '${clip.scene_id}'`,
        path: `${clipPath}.scene_id`
      });
      return;
    }
    clip.tracks.forEach((track, trackIndex) => {
      const trackPath = `${clipPath}.tracks[${trackIndex}]`;
      const characterId = sceneActors.get(track.actor_id);
      if (characterId === undefined) {
        issues.push({
          code: "CLIP_UNKNOWN_ACTOR",
          message: `track '${track.id}' references actor '${track.actor_id}' not present in scene '${clip.scene_id}'`,
          path: `${trackPath}.actor_id`
        });
        return;
      }
      const boneId =
        track.type === "bone_rotation" || track.type === "bone_scale" ? track.bone_id : null;
      const character = charactersById.get(characterId);
      if (boneId !== null && character !== undefined) {
        const boneIds = new Set(character.rig.bones.map((bone) => bone.id));
        if (!boneIds.has(boneId)) {
          issues.push({
            code: "CLIP_UNKNOWN_BONE",
            message: `track '${track.id}' references bone '${boneId}' missing from character '${characterId}'`,
            path: `${trackPath}.bone_id`
          });
        }
      }
    });
  });

  return issues;
}
