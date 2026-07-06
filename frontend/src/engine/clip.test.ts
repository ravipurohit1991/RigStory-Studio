import { describe, expect, it } from "vitest";

import bipedProjectJson from "@samples/projects/biped-demo.rigstory.json";
import { projectDocumentSchema, type AnimationClip } from "../schemas/project";
import {
  advanceClipTime,
  applyClipPoseToRig,
  clipLoopBounds,
  deleteKeyframe,
  duplicateKeyframe,
  evaluateClip,
  evaluateScalarKeyframes,
  evaluateVectorKeyframes,
  moveKeyframe,
  wrapClipTime
} from "./clip";

const document = projectDocumentSchema.parse(bipedProjectJson);
const clip = document.clips[0];

function angleClip(): AnimationClip {
  return {
    id: "clip_angle",
    scene_id: "scene_room",
    name: "Angle wrap",
    duration: 1,
    loop: false,
    loop_range: null,
    tracks: [
      {
        type: "bone_rotation",
        id: "track_angle",
        actor_id: "actor_mira",
        bone_id: "forearm_r",
        keyframes: [
          { id: "key_angle_0", time: 0, value: 359, interpolation: "linear" },
          { id: "key_angle_1", time: 1, value: 1, interpolation: "linear" }
        ]
      }
    ],
    events: [],
    markers: [],
    source_plan_id: null,
    engine_version: null
  };
}

describe("clip evaluation", () => {
  it("interpolates scalar, vector, and cubic keyframes deterministically", () => {
    expect(
      evaluateScalarKeyframes([
        { id: "key_a", time: 0, value: 0, interpolation: "linear" },
        { id: "key_b", time: 1, value: 10, interpolation: "linear" }
      ], 0.25)
    ).toBeCloseTo(2.5);

    expect(
      evaluateScalarKeyframes([
        { id: "key_a", time: 0, value: 0, interpolation: "stepped" },
        { id: "key_b", time: 1, value: 10, interpolation: "linear" }
      ], 0.75)
    ).toBe(0);

    expect(
      evaluateVectorKeyframes([
        { id: "key_a", time: 0, value: [0, 0], interpolation: "cubic" },
        { id: "key_b", time: 1, value: [10, 20], interpolation: "linear" }
      ], 0.5)
    ).toEqual([5, 10]);
  });

  it("takes the shortest path from 359 degrees to 1 degree", () => {
    const pose = evaluateClip(angleClip(), 0.5);
    expect(pose.actors.actor_mira.bone_rotations.forearm_r).toBeCloseTo(0);
  });

  it("wraps looped time and clamps non-looped time", () => {
    expect(wrapClipTime({ ...clip, loop: true }, 1.45)).toBeCloseTo(0.25);
    expect(wrapClipTime({ ...clip, loop: false }, 999)).toBe(clip.duration);
  });

  it("wraps playback inside an explicit loop range", () => {
    const ranged = { ...clip, loop: true, loop_range: [0.2, 0.8] as [number, number] };
    expect(clipLoopBounds(ranged)).toEqual({ start: 0.2, end: 0.8 });
    expect(wrapClipTime(ranged, 0.1)).toBeCloseTo(0.2);
    expect(wrapClipTime(ranged, 0.95)).toBeCloseTo(0.35);
    expect(advanceClipTime(ranged, 0.75, 0.1)).toBeCloseTo(0.25);
  });

  it("applies evaluated rotation tracks without mutating setup rig data", () => {
    const rig = document.characters[0].rig;
    const pose = evaluateClip(clip, 0.6);
    const animated = applyClipPoseToRig(rig, pose, "actor_mira");

    expect(animated).not.toBe(rig);
    expect(animated.bones.find((bone) => bone.id === "forearm_r")?.setup_transform.rotation_deg).toBe(60);
    expect(rig.bones.find((bone) => bone.id === "forearm_r")?.setup_transform.rotation_deg).toBe(4);
  });

  it("edits keyframes immutably and keeps time order valid", () => {
    const trackId = "track_wave_forearm_r";
    const moved = moveKeyframe(clip, trackId, "key_wave_2", 0.2);
    const movedTrack = moved.tracks.find((track) => track.id === trackId);
    expect(movedTrack?.keyframes.map((keyframe) => keyframe.id)).toEqual([
      "key_wave_0",
      "key_wave_2",
      "key_wave_1"
    ]);

    const duplicated = duplicateKeyframe(moved, trackId, "key_wave_1");
    expect(duplicated.tracks.find((track) => track.id === trackId)?.keyframes).toHaveLength(4);

    const deleted = deleteKeyframe(duplicated, trackId, "key_wave_1_copy");
    expect(deleted.tracks.find((track) => track.id === trackId)?.keyframes).toHaveLength(3);
  });
});
