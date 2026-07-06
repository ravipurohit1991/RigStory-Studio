import { normalizeDeg, shortestDeltaDeg } from "./math";
import type {
  AnimationClip,
  BoneDefinition,
  RigDefinition,
  TransformSpec
} from "../schemas/project";

type Track = AnimationClip["tracks"][number];
type Keyframe = Track["keyframes"][number];
type ScalarTrack = Extract<Track, { type: "bone_rotation" | "constraint_weight" }>;
type VectorTrack = Extract<Track, { type: "root_translation" | "bone_scale" }>;
type ScalarKeyframe = ScalarTrack["keyframes"][number];
type VectorKeyframe = VectorTrack["keyframes"][number];

export interface EvaluatedActorPose {
  readonly root_translation: readonly [number, number] | null;
  readonly bone_rotations: Readonly<Record<string, number>>;
  readonly bone_scales: Readonly<Record<string, readonly [number, number]>>;
  readonly constraint_weights: Readonly<Record<string, number>>;
}

export interface EvaluatedClipPose {
  readonly time: number;
  readonly actors: Readonly<Record<string, EvaluatedActorPose>>;
}

interface MutableActorPose {
  root_translation: readonly [number, number] | null;
  bone_rotations: Record<string, number>;
  bone_scales: Record<string, readonly [number, number]>;
  constraint_weights: Record<string, number>;
}

export interface ClipLoopBounds {
  readonly start: number;
  readonly end: number;
}

function clampTime(duration: number, time: number): number {
  return Math.min(Math.max(0, time), duration);
}

export function clipLoopBounds(clip: AnimationClip): ClipLoopBounds {
  if (clip.loop_range === null) {
    return { start: 0, end: clip.duration };
  }
  const start = clampTime(clip.duration, clip.loop_range[0]);
  const end = clampTime(clip.duration, clip.loop_range[1]);
  if (start >= end) {
    return { start: 0, end: clip.duration };
  }
  return { start, end };
}

export function wrapClipTime(clip: AnimationClip, time: number): number {
  if (!Number.isFinite(time)) {
    return 0;
  }
  if (!clip.loop) {
    return clampTime(clip.duration, time);
  }
  const { start, end } = clipLoopBounds(clip);
  if (time < start) {
    return start;
  }
  if (time <= end) {
    return time;
  }
  const span = end - start;
  const wrapped = (time - start) % span;
  return start + (wrapped < 0 ? wrapped + span : wrapped);
}

export function advanceClipTime(clip: AnimationClip, time: number, deltaSeconds: number): number {
  if (!Number.isFinite(time) || !Number.isFinite(deltaSeconds)) {
    return clip.loop ? clipLoopBounds(clip).start : 0;
  }
  if (!clip.loop) {
    return clampTime(clip.duration, time + deltaSeconds);
  }
  const { start, end } = clipLoopBounds(clip);
  const base = time < start || time > end ? start : time;
  return wrapClipTime(clip, base + deltaSeconds);
}

function interpolationWeight(interpolation: Keyframe["interpolation"], t: number): number {
  if (interpolation === "stepped") {
    return 0;
  }
  if (interpolation === "cubic") {
    return t * t * (3 - 2 * t);
  }
  return t;
}

function sortedKeyframes<TKey extends Keyframe>(keyframes: readonly TKey[]): TKey[] {
  return [...keyframes].sort((a, b) => a.time - b.time || a.id.localeCompare(b.id));
}

export function evaluateScalarKeyframes(
  keyframes: readonly ScalarKeyframe[],
  time: number,
  options: { readonly angle?: boolean } = {}
): number | null {
  if (keyframes.length === 0) {
    return null;
  }
  const sorted = sortedKeyframes(keyframes);
  if (time <= sorted[0].time) {
    return sorted[0].value;
  }
  const last = sorted.at(-1);
  if (last === undefined || time >= last.time) {
    return last?.value ?? sorted[0].value;
  }

  for (let index = 0; index < sorted.length - 1; index += 1) {
    const a = sorted[index];
    const b = sorted[index + 1];
    if (time < a.time || time > b.time) {
      continue;
    }
    const span = b.time - a.time;
    const t = span <= 0 ? 0 : interpolationWeight(a.interpolation, (time - a.time) / span);
    if (options.angle) {
      return normalizeDeg(a.value + shortestDeltaDeg(a.value, b.value) * t);
    }
    return a.value + (b.value - a.value) * t;
  }

  return sorted[0].value;
}

export function evaluateVectorKeyframes(
  keyframes: readonly VectorKeyframe[],
  time: number
): readonly [number, number] | null {
  if (keyframes.length === 0) {
    return null;
  }
  const sorted = sortedKeyframes(keyframes);
  if (time <= sorted[0].time) {
    return sorted[0].value;
  }
  const last = sorted.at(-1);
  if (last === undefined || time >= last.time) {
    return last?.value ?? sorted[0].value;
  }

  for (let index = 0; index < sorted.length - 1; index += 1) {
    const a = sorted[index];
    const b = sorted[index + 1];
    if (time < a.time || time > b.time) {
      continue;
    }
    const span = b.time - a.time;
    const t = span <= 0 ? 0 : interpolationWeight(a.interpolation, (time - a.time) / span);
    return [a.value[0] + (b.value[0] - a.value[0]) * t, a.value[1] + (b.value[1] - a.value[1]) * t];
  }

  return sorted[0].value;
}

function ensureActor(
  actors: Record<string, MutableActorPose>,
  actorId: string
): MutableActorPose {
  actors[actorId] ??= {
    root_translation: null,
    bone_rotations: {},
    bone_scales: {},
    constraint_weights: {}
  };
  return actors[actorId];
}

export function evaluateClip(clip: AnimationClip, time: number): EvaluatedClipPose {
  const sampleTime = wrapClipTime(clip, time);
  const actors: Record<string, MutableActorPose> = {};

  for (const track of clip.tracks) {
    const actor = ensureActor(actors, track.actor_id);
    if (track.type === "bone_rotation") {
      const value = evaluateScalarKeyframes(track.keyframes, sampleTime, { angle: true });
      if (value !== null) {
        actor.bone_rotations[track.bone_id] = value;
      }
    } else if (track.type === "root_translation") {
      actor.root_translation = evaluateVectorKeyframes(track.keyframes, sampleTime);
    } else if (track.type === "bone_scale") {
      const value = evaluateVectorKeyframes(track.keyframes, sampleTime);
      if (value !== null) {
        actor.bone_scales[track.bone_id] = value;
      }
    } else {
      const value = evaluateScalarKeyframes(track.keyframes, sampleTime);
      if (value !== null) {
        actor.constraint_weights[track.constraint_id] = value;
      }
    }
  }

  return { time: sampleTime, actors };
}

function applyBonePose(bone: BoneDefinition, pose: EvaluatedActorPose): BoneDefinition {
  const rotation = pose.bone_rotations[bone.id];
  const scale = pose.bone_scales[bone.id];
  if (rotation === undefined && scale === undefined) {
    return bone;
  }
  const transform: TransformSpec = {
    ...bone.setup_transform,
    rotation_deg: rotation ?? bone.setup_transform.rotation_deg,
    scale: scale === undefined ? bone.setup_transform.scale : [scale[0], scale[1]]
  };
  return { ...bone, setup_transform: transform };
}

export function applyClipPoseToRig(
  rig: RigDefinition,
  pose: EvaluatedClipPose,
  actorId: string
): RigDefinition {
  const actorPose = pose.actors[actorId];
  if (actorPose === undefined) {
    return rig;
  }
  return {
    ...rig,
    bones: rig.bones.map((bone) => applyBonePose(bone, actorPose))
  };
}

export function findTrack(clip: AnimationClip, trackId: string): Track | null {
  return clip.tracks.find((track) => track.id === trackId) ?? null;
}

export function sortTrackKeyframes<TClip extends AnimationClip>(clip: TClip): TClip {
  return {
    ...clip,
    tracks: clip.tracks.map((track) => {
      if (track.type === "bone_rotation") {
        return { ...track, keyframes: sortedKeyframes(track.keyframes) };
      }
      if (track.type === "root_translation") {
        return { ...track, keyframes: sortedKeyframes(track.keyframes) };
      }
      if (track.type === "bone_scale") {
        return { ...track, keyframes: sortedKeyframes(track.keyframes) };
      }
      return { ...track, keyframes: sortedKeyframes(track.keyframes) };
    })
  } as TClip;
}

export function moveKeyframe<TClip extends AnimationClip>(
  clip: TClip,
  trackId: string,
  keyframeId: string,
  time: number
): TClip {
  const clampedTime = Math.min(Math.max(0, time), clip.duration);
  return sortTrackKeyframes({
    ...clip,
    tracks: clip.tracks.map((track) => {
      if (track.id !== trackId) {
        return track;
      }
      let nextTime = clampedTime;
      const minimumGap = 0.001;
      while (
        track.keyframes.some(
          (keyframe) =>
            keyframe.id !== keyframeId && Math.abs(keyframe.time - nextTime) < minimumGap
        )
      ) {
        nextTime = Math.min(clip.duration, nextTime + minimumGap);
        if (nextTime >= clip.duration) {
          nextTime = Math.max(0, clampedTime - minimumGap);
          break;
        }
      }
      return {
        ...track,
        keyframes: track.keyframes.map((keyframe) =>
          keyframe.id === keyframeId ? { ...keyframe, time: nextTime } : keyframe
        )
      };
    })
  } as TClip);
}

export function deleteKeyframe<TClip extends AnimationClip>(
  clip: TClip,
  trackId: string,
  keyframeId: string
): TClip {
  return {
    ...clip,
    tracks: clip.tracks.map((track) =>
      track.id === trackId
        ? { ...track, keyframes: track.keyframes.filter((keyframe) => keyframe.id !== keyframeId) }
        : track
    )
  } as TClip;
}

export function duplicateKeyframe<TClip extends AnimationClip>(
  clip: TClip,
  trackId: string,
  keyframeId: string
): TClip {
  const track = findTrack(clip, trackId);
  const keyframe = track?.keyframes.find((candidate) => candidate.id === keyframeId);
  if (track === null || keyframe === undefined) {
    return clip;
  }
  const nextTime = Math.min(clip.duration, keyframe.time + 0.1);
  const nextKeyframe = {
    ...keyframe,
    id: `${keyframe.id}_copy`,
    time: nextTime
  };
  return sortTrackKeyframes({
    ...clip,
    tracks: clip.tracks.map((candidate) =>
      candidate.id === trackId
        ? { ...candidate, keyframes: [...candidate.keyframes, nextKeyframe] }
        : candidate
    )
  } as TClip);
}

export function upsertScalarKeyframe<TClip extends AnimationClip>(
  clip: TClip,
  trackId: string,
  keyframe: ScalarKeyframe
): TClip {
  return sortTrackKeyframes({
    ...clip,
    tracks: clip.tracks.map((track) => {
      if (track.id !== trackId) {
        return track;
      }
      const replaced = track.keyframes.some((existing) => existing.id === keyframe.id);
      return {
        ...track,
        keyframes: replaced
          ? track.keyframes.map((existing) => (existing.id === keyframe.id ? keyframe : existing))
          : [...track.keyframes, keyframe]
      };
    })
  } as TClip);
}
