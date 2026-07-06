/**
 * RigStory native runtime player.
 *
 * A minimal, versioned playback API that is independent of the editor UI:
 * no React, Fluent UI, or PixiJS imports. Give it a validated project
 * document (or raw JSON to validate) plus a canvas, and it plays a clip with
 * play / pause / seek / loop control and event callbacks.
 *
 * See docs/runtime.md for the integration example.
 */

import {
  advanceClipTime,
  clipLoopBounds,
  wrapClipTime
} from "../engine/clip";
import { projectDocumentSchema, type ProjectDocument } from "../schemas/project";
import {
  renderClipFrame,
  resolveClipSource,
  type Context2DLike,
  type RuntimeClipSource
} from "./renderer";

/** Semantic version of the public runtime API. */
export const RUNTIME_API_VERSION = "1.0.0";

export type RuntimePlayerEventName = "frame" | "finish" | "loop" | "clipevent";

export interface RuntimeClipEvent {
  readonly name: string;
  readonly time: number;
  readonly params: Readonly<Record<string, string | number | boolean>>;
}

interface RuntimePlayerEventMap {
  frame: (time: number) => void;
  finish: () => void;
  loop: () => void;
  clipevent: (event: RuntimeClipEvent) => void;
}

export interface CanvasLike {
  readonly width: number;
  readonly height: number;
  getContext(kind: "2d"): Context2DLike | null;
}

export interface RigStoryPlayerOptions {
  /** A parsed project document or raw JSON; both are validated. */
  readonly document: unknown;
  /** Clip to play; defaults to the first clip in the project. */
  readonly clipId?: string;
  readonly canvas?: CanvasLike;
  /** Explicit context override (useful for headless rendering and tests). */
  readonly context?: Context2DLike;
  readonly width?: number;
  readonly height?: number;
  /** CSS background color, or null/undefined for transparent frames. */
  readonly background?: string | null;
  /** Override the clip's own loop flag. */
  readonly loop?: boolean;
  /** Frame scheduler; defaults to requestAnimationFrame. Injectable for tests. */
  readonly schedule?: (callback: (timestampMs: number) => void) => number;
  readonly cancel?: (handle: number) => void;
}

/** Validate untrusted JSON into a project document for runtime playback. */
export function loadRuntimeDocument(raw: unknown): ProjectDocument {
  return projectDocumentSchema.parse(raw);
}

export interface RigStoryPlayer {
  readonly apiVersion: string;
  readonly duration: number;
  readonly clipId: string;
  readonly sceneId: string;
  readonly time: number;
  readonly playing: boolean;
  readonly loop: boolean;
  play(): void;
  pause(): void;
  seek(time: number): void;
  setLoop(loop: boolean): void;
  /** Render the current (or given) time without changing playback state. */
  renderFrame(time?: number): void;
  on<TName extends RuntimePlayerEventName>(
    name: TName,
    listener: RuntimePlayerEventMap[TName]
  ): () => void;
  dispose(): void;
}

class PlayerImpl implements RigStoryPlayer {
  readonly apiVersion = RUNTIME_API_VERSION;
  private readonly source: RuntimeClipSource;
  private readonly ctx: Context2DLike;
  private readonly width: number;
  private readonly height: number;
  private readonly background: string | null;
  private readonly schedule: (callback: (timestampMs: number) => void) => number;
  private readonly cancel: (handle: number) => void;
  private readonly listeners: {
    [TName in RuntimePlayerEventName]: Set<RuntimePlayerEventMap[TName]>;
  } = { frame: new Set(), finish: new Set(), loop: new Set(), clipevent: new Set() };

  private currentTime = 0;
  private isPlaying = false;
  private loopEnabled: boolean;
  private frameHandle: number | null = null;
  private lastTimestampMs: number | null = null;
  private disposed = false;

  constructor(options: RigStoryPlayerOptions) {
    const document = loadRuntimeDocument(options.document);
    this.source = resolveClipSource(document, options.clipId);
    const context = options.context ?? options.canvas?.getContext("2d") ?? null;
    if (context === null) {
      throw new Error("a canvas or 2d context is required to create a player");
    }
    this.ctx = context;
    this.width = options.width ?? options.canvas?.width ?? 640;
    this.height = options.height ?? options.canvas?.height ?? 480;
    this.background = options.background ?? null;
    this.loopEnabled = options.loop ?? this.source.clip.loop;
    this.schedule =
      options.schedule ??
      ((callback) => globalThis.requestAnimationFrame(callback));
    this.cancel =
      options.cancel ?? ((handle) => globalThis.cancelAnimationFrame(handle));
    this.currentTime = this.loopEnabled ? clipLoopBounds(this.source.clip).start : 0;
    this.renderFrame();
  }

  get duration(): number {
    return this.source.clip.duration;
  }

  get clipId(): string {
    return this.source.clip.id;
  }

  get sceneId(): string {
    return this.source.scene.id;
  }

  get time(): number {
    return this.currentTime;
  }

  get playing(): boolean {
    return this.isPlaying;
  }

  get loop(): boolean {
    return this.loopEnabled;
  }

  play(): void {
    if (this.disposed || this.isPlaying) {
      return;
    }
    if (!this.loopEnabled && this.currentTime >= this.duration) {
      this.currentTime = 0;
    }
    this.isPlaying = true;
    this.lastTimestampMs = null;
    this.requestTick();
  }

  pause(): void {
    this.isPlaying = false;
    this.lastTimestampMs = null;
    if (this.frameHandle !== null) {
      this.cancel(this.frameHandle);
      this.frameHandle = null;
    }
  }

  seek(time: number): void {
    if (this.disposed) {
      return;
    }
    this.currentTime = this.loopEnabled
      ? wrapClipTime({ ...this.source.clip, loop: true }, time)
      : Math.min(Math.max(0, time), this.duration);
    this.renderFrame();
    this.emitFrame();
  }

  setLoop(loop: boolean): void {
    this.loopEnabled = loop;
  }

  renderFrame(time?: number): void {
    if (this.disposed) {
      return;
    }
    renderClipFrame(this.ctx, this.source, time ?? this.currentTime, {
      width: this.width,
      height: this.height,
      background: this.background
    });
  }

  on<TName extends RuntimePlayerEventName>(
    name: TName,
    listener: RuntimePlayerEventMap[TName]
  ): () => void {
    this.listeners[name].add(listener);
    return () => {
      this.listeners[name].delete(listener);
    };
  }

  dispose(): void {
    this.pause();
    this.disposed = true;
    for (const set of Object.values(this.listeners)) {
      set.clear();
    }
  }

  private requestTick(): void {
    this.frameHandle = this.schedule((timestampMs) => this.tick(timestampMs));
  }

  private tick(timestampMs: number): void {
    if (this.disposed || !this.isPlaying) {
      return;
    }
    const deltaSeconds =
      this.lastTimestampMs === null ? 0 : (timestampMs - this.lastTimestampMs) / 1000;
    this.lastTimestampMs = timestampMs;

    const previousTime = this.currentTime;
    const clip = { ...this.source.clip, loop: this.loopEnabled };
    const nextTime = advanceClipTime(clip, previousTime, deltaSeconds);
    const wrapped = this.loopEnabled && nextTime < previousTime;
    this.currentTime = nextTime;

    this.fireClipEvents(previousTime, nextTime, wrapped);
    this.renderFrame();
    this.emitFrame();

    if (wrapped) {
      for (const listener of this.listeners.loop) {
        listener();
      }
    }
    if (!this.loopEnabled && nextTime >= this.duration) {
      this.isPlaying = false;
      for (const listener of this.listeners.finish) {
        listener();
      }
      return;
    }
    this.requestTick();
  }

  private fireClipEvents(previousTime: number, nextTime: number, wrapped: boolean): void {
    const events = this.source.clip.events;
    if (events.length === 0 || (previousTime === nextTime && !wrapped)) {
      return;
    }
    const bounds = clipLoopBounds(this.source.clip);
    const inRange = (event: RuntimeClipEvent, start: number, end: number) =>
      event.time > start && event.time <= end;
    for (const event of events) {
      const fired = wrapped
        ? inRange(event, previousTime, bounds.end) || inRange(event, bounds.start - 1e-9, nextTime)
        : inRange(event, previousTime, nextTime);
      if (fired) {
        for (const listener of this.listeners.clipevent) {
          listener(event);
        }
      }
    }
  }

  private emitFrame(): void {
    for (const listener of this.listeners.frame) {
      listener(this.currentTime);
    }
  }
}

/** Create a player for one clip of a project document. */
export function createPlayer(options: RigStoryPlayerOptions): RigStoryPlayer {
  return new PlayerImpl(options);
}
