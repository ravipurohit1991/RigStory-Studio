# Native Runtime And Media Export

RigStory ships a small TypeScript runtime under `frontend/src/runtime`. It is
independent of React, Fluent UI, PixiJS, and editor state. It accepts a
validated native project document, resolves a scene plus clip, and renders to a
Canvas 2D context.

## Runtime API

```ts
import { createPlayer, RUNTIME_API_VERSION } from "./runtime";

const player = createPlayer({
  document: rigstoryProjectJson,
  clipId: "clip_wave",
  canvas: document.querySelector("canvas"),
  loop: true,
  background: "#ffffff"
});

player.on("clipevent", (event) => {
  console.log(event.name, event.time, event.params);
});

console.log(RUNTIME_API_VERSION);
player.play();
```

The public runtime surface is versioned by `RUNTIME_API_VERSION`. Breaking
changes require a major version bump.

## Controls

- `play()` starts playback.
- `pause()` stops scheduling frames.
- `seek(seconds)` moves the playhead and renders immediately.
- `setLoop(enabled)` controls loop behavior independently of the stored clip.
- `renderFrame(seconds?)` renders one frame without changing playback state.
- `dispose()` cancels playback and clears listeners.

## Media Export API

Backend media export is exposed as a long-running job:

```http
POST /api/v1/clips/{clip_id}/export
```

Request:

```json
{
  "format": "png_sequence",
  "frame_rate": 24,
  "width": 1280,
  "height": 720,
  "background": "#ffffff",
  "transparent": false
}
```

Supported formats are `png_sequence`, `animated_svg`, and `webm`. The job result
contains a `download_url`, checksum, frame count, frame rate, dimensions, and
duration. Export artifacts are written to a temporary directory first and are
published only after the job succeeds, so cancellation leaves no downloadable
partial file.
