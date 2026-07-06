/**
 * RigStory native runtime — public API surface (versioned).
 *
 * Everything exported here is safe to consume outside the editor. Breaking
 * changes to these exports require a RUNTIME_API_VERSION major bump.
 */

export {
  createPlayer,
  loadRuntimeDocument,
  RUNTIME_API_VERSION,
  type CanvasLike,
  type RigStoryPlayer,
  type RigStoryPlayerOptions,
  type RuntimeClipEvent,
  type RuntimePlayerEventName
} from "./player";
export {
  computeWorldToCanvas,
  renderClipFrame,
  resolveClipSource,
  RuntimeSourceError,
  type Context2DLike,
  type RenderFrameOptions,
  type RuntimeClipSource
} from "./renderer";
