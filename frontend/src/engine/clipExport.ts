import { evaluateClip } from "./clip";
import { computeBoneEndpoints } from "./rig";
import type { AnimationClip, CharacterDefinition } from "../schemas/project";
import { clipSchema } from "../schemas/project";

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => `${JSON.stringify(key)}:${stableStringify(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

export function exportClipJson(clip: AnimationClip): string {
  return stableStringify(clip);
}

export function importClipJson(raw: string): AnimationClip {
  return clipSchema.parse(JSON.parse(raw));
}

export function exportRigidAnimatedSvg(options: {
  readonly clip: AnimationClip;
  readonly character: CharacterDefinition;
  readonly actorId: string;
  readonly width?: number;
  readonly height?: number;
}): string {
  const width = options.width ?? 640;
  const height = options.height ?? 480;
  const samples = Array.from(new Set([0, options.clip.duration / 2, options.clip.duration]))
    .sort((a, b) => a - b);
  const valuesByBone = new Map<string, string[]>();
  const keyTimes = samples.map((time) => (time / options.clip.duration).toFixed(4)).join(";");

  for (const sample of samples) {
    const pose = evaluateClip(options.clip, sample);
    const actorPose = pose.actors[options.actorId];
    for (const [boneId, value] of Object.entries(actorPose?.bone_rotations ?? {})) {
      valuesByBone.set(boneId, [...(valuesByBone.get(boneId) ?? []), value.toFixed(3)]);
    }
  }

  const endpoints = computeBoneEndpoints(options.character.rig);
  const lines = options.character.rig.bones
    .map((bone) => {
      const endpoint = endpoints.get(bone.id);
      if (endpoint === undefined || bone.length === 0) {
        return "";
      }
      const values = valuesByBone.get(bone.id);
      const animation =
        values === undefined
          ? ""
          : `<animateTransform attributeName="transform" type="rotate" dur="${options.clip.duration}s" values="${values.join(";")}" keyTimes="${keyTimes}" repeatCount="${options.clip.loop ? "indefinite" : "1"}" />`;
      return [
        `<g id="bone_${escapeXml(bone.id)}">`,
        animation,
        `<line x1="${(endpoint.origin.x * 80).toFixed(2)}" y1="${(-endpoint.origin.y * 80).toFixed(2)}" x2="${(endpoint.tip.x * 80).toFixed(2)}" y2="${(-endpoint.tip.y * 80).toFixed(2)}" stroke="#355c7d" stroke-width="6" stroke-linecap="round" />`,
        "</g>"
      ].join("");
    })
    .join("");

  return [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="-320 -360 640 480" role="img" aria-label="${escapeXml(options.clip.name)}">`,
    `<title>${escapeXml(options.clip.name)}</title>`,
    lines,
    "</svg>"
  ].join("");
}
