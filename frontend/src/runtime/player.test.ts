import { describe, expect, it } from "vitest";

import { createPlayer, loadRuntimeDocument, RUNTIME_API_VERSION } from "./index";
import {
  computeWorldToCanvas,
  primitiveOutlinePoints,
  resolveClipSource,
  RuntimeSourceError,
  worldPointToCanvas,
  type Context2DLike
} from "./renderer";
import { readSample } from "../test-utils/samples";

interface RecordedCall {
  readonly op: string;
  readonly args: readonly number[];
}

function fakeContext(): { ctx: Context2DLike; calls: RecordedCall[] } {
  const calls: RecordedCall[] = [];
  const record =
    (op: string) =>
    (...args: number[]) => {
      calls.push({ op, args });
    };
  const ctx: Context2DLike = {
    fillStyle: "#000000",
    strokeStyle: "#000000",
    globalAlpha: 1,
    lineWidth: 1,
    lineCap: "butt",
    clearRect: record("clearRect"),
    fillRect: record("fillRect"),
    beginPath: record("beginPath"),
    moveTo: record("moveTo"),
    lineTo: record("lineTo"),
    closePath: record("closePath"),
    fill: record("fill"),
    stroke: record("stroke")
  };
  return { ctx, calls };
}

/** Manual frame scheduler so tests control playback time deterministically. */
function manualScheduler() {
  const pending = new Map<number, (timestampMs: number) => void>();
  let nextHandle = 1;
  return {
    schedule(callback: (timestampMs: number) => void): number {
      const handle = nextHandle;
      nextHandle += 1;
      pending.set(handle, callback);
      return handle;
    },
    cancel(handle: number): void {
      pending.delete(handle);
    },
    step(timestampMs: number): void {
      const callbacks = [...pending.values()];
      pending.clear();
      for (const callback of callbacks) {
        callback(timestampMs);
      }
    },
    get pendingCount(): number {
      return pending.size;
    }
  };
}

const rawDocument = readSample("projects/biped-demo.rigstory.json");

describe("runtime document loading", () => {
  it("validates and resolves a clip with its scene and characters", () => {
    const document = loadRuntimeDocument(rawDocument);
    const source = resolveClipSource(document, "clip_wave");
    expect(source.scene.id).toBe("scene_room");
    expect(source.actors.map((actor) => actor.actorId)).toEqual(["actor_mira"]);
  });

  it("rejects unknown clips with a clear error", () => {
    const document = loadRuntimeDocument(rawDocument);
    expect(() => resolveClipSource(document, "clip_missing")).toThrow(RuntimeSourceError);
  });

  it("rejects documents that fail schema validation", () => {
    expect(() => loadRuntimeDocument({ format: "rigstory-project" })).toThrow();
  });
});

describe("world-to-canvas mapping", () => {
  it("fits Y-up world bounds into a Y-down canvas", () => {
    const map = computeWorldToCanvas([-2, 0, 2, 4], 400, 400, 0);
    const bottomLeft = worldPointToCanvas(map, { x: -2, y: 0 });
    const topRight = worldPointToCanvas(map, { x: 2, y: 4 });
    expect(bottomLeft.x).toBeCloseTo(0);
    expect(bottomLeft.y).toBeCloseTo(400);
    expect(topRight.x).toBeCloseTo(400);
    expect(topRight.y).toBeCloseTo(0);
  });
});

describe("primitive outlines", () => {
  it("builds rectangle corners around the pivot", () => {
    const points = primitiveOutlinePoints(
      { shape: "rectangle", size: [2, 1], fill: "#ffffff", opacity: 1 },
      [0.5, 0]
    );
    expect(points).toHaveLength(4);
    expect(points[0]).toEqual({ x: -0.5, y: -0.5 });
    expect(points[2]).toEqual({ x: 1.5, y: 0.5 });
  });

  it("keeps ellipse and capsule outlines closed and finite", () => {
    for (const shape of ["ellipse", "capsule"] as const) {
      const points = primitiveOutlinePoints(
        { shape, size: [1.2, 0.4], fill: "#ffffff", opacity: 1 },
        [0, 0]
      );
      expect(points).toHaveLength(24);
      expect(points.every((point) => Number.isFinite(point.x) && Number.isFinite(point.y))).toBe(
        true
      );
    }
  });
});

describe("runtime player", () => {
  it("exposes the versioned API and renders an initial frame", () => {
    const { ctx, calls } = fakeContext();
    const player = createPlayer({
      document: rawDocument,
      clipId: "clip_wave",
      context: ctx,
      width: 320,
      height: 240
    });
    expect(player.apiVersion).toBe(RUNTIME_API_VERSION);
    expect(RUNTIME_API_VERSION).toMatch(/^\d+\.\d+\.\d+$/);
    expect(player.duration).toBeCloseTo(1.2);
    expect(player.playing).toBe(false);
    expect(calls.some((call) => call.op === "clearRect")).toBe(true);
    expect(calls.some((call) => call.op === "fill")).toBe(true);
    player.dispose();
  });

  it("plays, advances deterministically, and finishes without looping", () => {
    const { ctx } = fakeContext();
    const scheduler = manualScheduler();
    const player = createPlayer({
      document: rawDocument,
      clipId: "clip_wave",
      context: ctx,
      width: 320,
      height: 240,
      schedule: scheduler.schedule,
      cancel: scheduler.cancel
    });
    const frames: number[] = [];
    let finished = 0;
    player.on("frame", (time) => frames.push(time));
    player.on("finish", () => {
      finished += 1;
    });

    player.play();
    scheduler.step(0); // first tick establishes the timestamp baseline
    scheduler.step(500);
    expect(player.time).toBeCloseTo(0.5);
    scheduler.step(1000);
    expect(player.time).toBeCloseTo(1.0);
    scheduler.step(1500);
    expect(player.time).toBeCloseTo(1.2);
    expect(player.playing).toBe(false);
    expect(finished).toBe(1);
    expect(scheduler.pendingCount).toBe(0);
    expect(frames.at(-1)).toBeCloseTo(1.2);
    player.dispose();
  });

  it("loops when requested and reports the wrap", () => {
    const { ctx } = fakeContext();
    const scheduler = manualScheduler();
    const player = createPlayer({
      document: rawDocument,
      clipId: "clip_wave",
      context: ctx,
      width: 320,
      height: 240,
      loop: true,
      schedule: scheduler.schedule,
      cancel: scheduler.cancel
    });
    let loops = 0;
    player.on("loop", () => {
      loops += 1;
    });

    player.play();
    scheduler.step(0);
    scheduler.step(1100);
    expect(player.time).toBeCloseTo(1.1);
    scheduler.step(1400); // wraps past the 1.2s duration
    expect(loops).toBe(1);
    expect(player.time).toBeCloseTo(0.2);
    expect(player.playing).toBe(true);
    player.pause();
    expect(scheduler.pendingCount).toBe(0);
    player.dispose();
  });

  it("seeks with clamping and re-renders", () => {
    const { ctx, calls } = fakeContext();
    const player = createPlayer({
      document: rawDocument,
      clipId: "clip_wave",
      context: ctx,
      width: 320,
      height: 240
    });
    calls.length = 0;
    player.seek(99);
    expect(player.time).toBeCloseTo(1.2);
    player.seek(-1);
    expect(player.time).toBe(0);
    expect(calls.filter((call) => call.op === "clearRect").length).toBe(2);
    player.dispose();
  });

  it("paints an opaque background only when configured", () => {
    const { ctx, calls } = fakeContext();
    const player = createPlayer({
      document: rawDocument,
      clipId: "clip_wave",
      context: ctx,
      width: 320,
      height: 240,
      background: "#101418"
    });
    const fullFrameFills = calls.filter(
      (call) => call.op === "fillRect" && call.args[2] === 320 && call.args[3] === 240
    );
    expect(fullFrameFills.length).toBe(1);
    player.dispose();
  });
});
