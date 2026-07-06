import {
  Badge,
  Body1,
  Button,
  Caption1,
  Field,
  Input,
  Radio,
  RadioGroup,
  Select,
  Switch,
  Text,
  Title3,
  Tooltip
} from "@fluentui/react-components";
import {
  Copy,
  Crosshair,
  Download,
  FileUp,
  Maximize2,
  Pause,
  Play,
  Plus,
  Redo2,
  Save,
  SkipBack,
  SkipForward,
  Trash2,
  Undo2
} from "lucide-react";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import bipedProjectJson from "@samples/projects/biped-demo.rigstory.json";
import {
  createProject,
  duplicateProject,
  getProject,
  updateProject
} from "../api/client";
import {
  createEmptyHistory,
  createReplaceStateCommand,
  redo,
  runCommand,
  undo,
  type EditorCommand,
  type EditorHistory
} from "../editor/commands";
import {
  createPrimitiveAttachment,
  isSafePngDataUrl,
  sanitizeSvgMarkup,
  updateAttachment
} from "../engine/attachments";
import {
  advanceClipTime,
  applyClipPoseToRig,
  clipLoopBounds,
  deleteKeyframe,
  duplicateKeyframe,
  evaluateClip,
  evaluateScalarKeyframes,
  moveKeyframe,
  upsertScalarKeyframe,
  type ClipLoopBounds
} from "../engine/clip";
import {
  exportClipJson,
  exportRigidAnimatedSvg,
  importClipJson
} from "../engine/clipExport";
import { rotationDegOf } from "../engine/math";
import { computeBoneEndpoints, computeWorldTransforms, type BoneLike } from "../engine/rig";
import {
  editBoneBodyByWorldDelta,
  editBoneEndpointToWorldPoint,
  getDescendantBoneIds,
  reparentBone,
  setBoneLength,
  setBoneLocalPosition,
  setBoneLocalRotation,
  type RigEditMode
} from "../engine/rigEditing";
import type {
  RigStageAdapterHandle,
  RigStageBoneDragEvent,
  RigStageOnionSkin,
  RigStageUpdate
} from "../engine/renderer/RigStageAdapter";
import {
  DEFAULT_STAGE_CAMERA,
  normalizeViewportSize,
  type WorldBounds
} from "../engine/renderer/viewport";
import {
  projectDocumentSchema,
  type AnimationClip,
  type AttachmentDefinition,
  type CharacterDefinition,
  type ProjectDocument,
  type RigDefinition
} from "../schemas/project";

const INITIAL_DOCUMENT = projectDocumentSchema.parse(bipedProjectJson);
const INITIAL_SELECTED_BONE_ID = "hips";
const INITIAL_SHOW_LABELS = true;
const INITIAL_SHOW_DEBUG_AXES = true;

type Track = AnimationClip["tracks"][number];
type Keyframe = Track["keyframes"][number];

function formatNumber(value: number): string {
  return value.toFixed(3);
}

function formatEditableNumber(value: number): string {
  if (Number.isInteger(value)) {
    return String(value);
  }
  return value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

function formatPair(x: number, y: number): string {
  return `${formatNumber(x)}, ${formatNumber(y)}`;
}

function timelinePercent(time: number, duration: number): string {
  return `${duration <= 0 ? 0 : (time / duration) * 100}%`;
}

function commandIdForLabel(label: string): string {
  return `project.${label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "")}`;
}

function createDocumentCommand(
  document: ProjectDocument,
  label: string,
  mergeKey?: string
): EditorCommand<ProjectDocument> {
  return createReplaceStateCommand({
    id: commandIdForLabel(label),
    label,
    state: document,
    mergeKey
  });
}

interface RigEditorState {
  readonly document: ProjectDocument;
  readonly history: EditorHistory<ProjectDocument>;
  readonly dirty: boolean;
}

type RigEditorAction =
  | {
      readonly type: "run";
      readonly command: EditorCommand<ProjectDocument>;
      readonly mergeWithPrevious?: boolean;
    }
  | { readonly type: "undo" }
  | { readonly type: "redo" }
  | { readonly type: "load"; readonly document: ProjectDocument }
  | { readonly type: "markSaved" };

function rigEditorReducer(state: RigEditorState, action: RigEditorAction): RigEditorState {
  if (action.type === "load") {
    return {
      document: action.document,
      history: createEmptyHistory<ProjectDocument>(),
      dirty: false
    };
  }
  if (action.type === "markSaved") {
    return { ...state, dirty: false };
  }
  if (action.type === "undo") {
    const result = undo(state.document, state.history);
    return result.state === state.document
      ? state
      : { document: result.state, history: result.history, dirty: true };
  }
  if (action.type === "redo") {
    const result = redo(state.document, state.history);
    return result.state === state.document
      ? state
      : { document: result.state, history: result.history, dirty: true };
  }

  const result = runCommand(state.document, state.history, action.command, {
    mergeWithPrevious: action.mergeWithPrevious
  });
  return result.state === state.document
    ? state
    : { document: result.state, history: result.history, dirty: true };
}

function createInitialEditorState(): RigEditorState {
  return {
    document: INITIAL_DOCUMENT,
    history: createEmptyHistory<ProjectDocument>(),
    dirty: false
  };
}

function activeCharacter(document: ProjectDocument): CharacterDefinition {
  return document.characters[0];
}

function activeClip(document: ProjectDocument): AnimationClip | null {
  return document.clips[0] ?? null;
}

function cameraBoundsFor(document: ProjectDocument): WorldBounds {
  const scene = document.scenes[0];
  return scene?.world_bounds ?? [-2.5, -0.35, 2.5, 4.25];
}

function actorIdForClip(
  document: ProjectDocument,
  characterId: string,
  clip: AnimationClip | null
): string | null {
  if (clip === null) {
    return document.scenes.flatMap((scene) => scene.actors).find((actor) => actor.character_id === characterId)?.id ?? null;
  }
  const scene = document.scenes.find((candidate) => candidate.id === clip.scene_id);
  return scene?.actors.find((actor) => actor.character_id === characterId)?.id ?? null;
}

function replaceCharacter(
  document: ProjectDocument,
  character: CharacterDefinition
): ProjectDocument {
  return {
    ...document,
    characters: document.characters.map((candidate, index) =>
      index === 0 ? character : candidate
    )
  };
}

function replaceRig(document: ProjectDocument, rig: RigDefinition): ProjectDocument {
  return replaceCharacter(document, { ...activeCharacter(document), rig });
}

function replaceAttachments(
  document: ProjectDocument,
  attachments: readonly AttachmentDefinition[]
): ProjectDocument {
  return replaceCharacter(document, {
    ...activeCharacter(document),
    attachments: [...attachments]
  });
}

function replaceClip(document: ProjectDocument, clip: AnimationClip): ProjectDocument {
  return {
    ...document,
    clips: document.clips.map((candidate, index) => (index === 0 ? clip : candidate))
  };
}

function clampClipTime(clip: AnimationClip, time: number): number {
  if (!Number.isFinite(time)) {
    return 0;
  }
  return Math.min(Math.max(0, time), clip.duration);
}

function clampLoopRangeValue(clip: AnimationClip, value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(Math.max(0, value), clip.duration);
}

function updateClipLoopRange(
  clip: AnimationClip,
  partial: Partial<ClipLoopBounds>
): AnimationClip {
  const current = clipLoopBounds(clip);
  let start = clampLoopRangeValue(clip, partial.start ?? current.start);
  let end = clampLoopRangeValue(clip, partial.end ?? current.end);
  const minimumSpan = Math.min(0.01, clip.duration);
  if (end <= start) {
    if (partial.start !== undefined) {
      start = Math.max(0, end - minimumSpan);
    } else {
      end = Math.min(clip.duration, start + minimumSpan);
    }
  }
  return { ...clip, loop: true, loop_range: [start, end] };
}

function displayRigAtTime(
  rig: RigDefinition,
  clip: AnimationClip | null,
  actorId: string | null,
  time: number
): RigDefinition {
  if (clip === null || actorId === null) {
    return rig;
  }
  return applyClipPoseToRig(rig, evaluateClip(clip, time), actorId);
}

function onionSkinRigs(
  rig: RigDefinition,
  clip: AnimationClip | null,
  actorId: string | null,
  time: number,
  enabled: boolean
): RigStageOnionSkin[] {
  if (!enabled || clip === null || actorId === null) {
    return [];
  }
  const samples = [
    { offset: -0.2, alpha: 0.22 },
    { offset: 0.2, alpha: 0.16 }
  ];
  return samples.map((sample) => {
    const sampleTime = clip.loop
      ? advanceClipTime(clip, time, sample.offset)
      : clampClipTime(clip, time + sample.offset);
    return {
      rig: displayRigAtTime(rig, clip, actorId, sampleTime),
      alpha: sample.alpha
    };
  });
}

function buildChildrenByParent(bones: readonly BoneLike[]): Map<string | null, BoneLike[]> {
  const childrenByParent = new Map<string | null, BoneLike[]>();
  for (const bone of bones) {
    const siblings = childrenByParent.get(bone.parent_id) ?? [];
    siblings.push(bone);
    childrenByParent.set(bone.parent_id, siblings);
  }
  return childrenByParent;
}

function trackLabel(track: Track): string {
  if (track.type === "bone_rotation") {
    return `${track.actor_id} / ${track.bone_id} rotation`;
  }
  if (track.type === "bone_scale") {
    return `${track.actor_id} / ${track.bone_id} scale`;
  }
  if (track.type === "root_translation") {
    return `${track.actor_id} root`;
  }
  return `${track.actor_id} / ${track.constraint_id} weight`;
}

function keyframeDisplayValue(keyframe: Keyframe): string {
  return Array.isArray(keyframe.value)
    ? `[${keyframe.value.map((value) => formatNumber(value)).join(", ")}]`
    : formatNumber(keyframe.value);
}

function scalarTrackValue(track: Track, time: number): number | null {
  if (track.type !== "bone_rotation" && track.type !== "constraint_weight") {
    return null;
  }
  return evaluateScalarKeyframes(track.keyframes, time, { angle: track.type === "bone_rotation" });
}

function scalarTrackVelocity(track: Track, time: number, duration: number): number | null {
  const delta = Math.min(0.01, duration / 100);
  if (delta <= 0) {
    return null;
  }
  const before = scalarTrackValue(track, Math.max(0, time - delta));
  const after = scalarTrackValue(track, Math.min(duration, time + delta));
  if (before === null || after === null) {
    return null;
  }
  return (after - before) / (Math.min(duration, time + delta) - Math.max(0, time - delta));
}

function scalarCurvePolyline(track: Track, duration: number): string | null {
  if (track.type !== "bone_rotation" && track.type !== "constraint_weight") {
    return null;
  }
  const values = Array.from({ length: 33 }, (_value, index) => {
    const time = (duration * index) / 32;
    return scalarTrackValue(track, time) ?? 0;
  });
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const span = Math.max(1e-6, maxValue - minValue);
  return values
    .map((value, index) => {
      const x = (index / 32) * 160;
      const y = 44 - ((value - minValue) / span) * 36;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

function scalarTrackId(actorId: string, boneId: string): string {
  return `track_${actorId.replace(/^actor_/, "")}_${boneId.replace(/[^a-z0-9_]/g, "_")}_rot`;
}

function keyframeId(trackId: string, time: number): string {
  return `key_${trackId.replace(/^track_/, "")}_${Math.round(time * 1000)}`;
}

function setBoneRotationKeyframe(
  document: ProjectDocument,
  actorId: string,
  boneId: string,
  time: number,
  value: number
): ProjectDocument {
  const clip = activeClip(document);
  if (clip === null) {
    return document;
  }
  const track =
    clip.tracks.find(
      (candidate) =>
        candidate.type === "bone_rotation" &&
        candidate.actor_id === actorId &&
        candidate.bone_id === boneId
    ) ?? null;
  const targetTrackId = track?.id ?? scalarTrackId(actorId, boneId);
  const existingKey =
    track?.keyframes.find((keyframe) => Math.abs(keyframe.time - time) < 1e-6) ?? null;
  const keyframe = {
    id: existingKey?.id ?? keyframeId(targetTrackId, time),
    time,
    value,
    interpolation: "linear" as const
  };

  if (track === null) {
    return replaceClip(document, {
      ...clip,
      tracks: [
        ...clip.tracks,
        {
          type: "bone_rotation",
          id: targetTrackId,
          actor_id: actorId,
          bone_id: boneId,
          keyframes: [keyframe]
        }
      ]
    });
  }
  return replaceClip(document, upsertScalarKeyframe(clip, targetTrackId, keyframe));
}

function updateSelectedKeyframe(
  document: ProjectDocument,
  trackId: string,
  keyframeIdValue: string,
  update: (keyframe: Keyframe) => Keyframe
): ProjectDocument {
  const clip = activeClip(document);
  if (clip === null) {
    return document;
  }
  const tracks = clip.tracks.map((track) =>
    track.id === trackId
      ? {
          ...track,
          keyframes: [
            ...track.keyframes.map((keyframe) =>
              keyframe.id === keyframeIdValue ? update(keyframe) : keyframe
            )
          ].sort((a, b) => a.time - b.time || a.id.localeCompare(b.id))
        }
      : track
  ) as AnimationClip["tracks"];
  return replaceClip(document, {
    ...clip,
    tracks
  });
}

async function fileSha256Hex(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("file could not be read"));
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.readAsText(file);
  });
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("file could not be read"));
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.readAsDataURL(file);
  });
}

function downloadText(filename: string, text: string, mediaType: string): void {
  const blob = new Blob([text], { type: mediaType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

interface BoneTreeProps {
  readonly parentId: string | null;
  readonly childrenByParent: Map<string | null, BoneLike[]>;
  readonly selectedBoneId: string | null;
  readonly onSelectBone: (boneId: string) => void;
  readonly depth?: number;
}

function BoneTree({
  parentId,
  childrenByParent,
  selectedBoneId,
  onSelectBone,
  depth = 0
}: BoneTreeProps) {
  const bones = childrenByParent.get(parentId) ?? [];
  if (bones.length === 0) {
    return null;
  }
  return (
    <ul className={depth === 0 ? "bone-tree" : "bone-tree bone-tree-nested"}>
      {bones.map((bone) => (
        <li key={bone.id}>
          <button
            type="button"
            className="bone-tree-button"
            aria-pressed={bone.id === selectedBoneId}
            style={{ paddingLeft: `${10 + depth * 14}px` }}
            onClick={() => onSelectBone(bone.id)}
          >
            <span>{bone.id}</span>
            <Caption1 className="muted-text">{bone.length.toFixed(2)} u</Caption1>
          </button>
          <BoneTree
            parentId={bone.id}
            childrenByParent={childrenByParent}
            selectedBoneId={selectedBoneId}
            onSelectBone={onSelectBone}
            depth={depth + 1}
          />
        </li>
      ))}
    </ul>
  );
}

interface NumberInputFieldProps {
  readonly label: string;
  readonly value: number;
  readonly disabled?: boolean;
  readonly min?: number;
  readonly max?: number;
  readonly step?: number;
  readonly onCommit: (value: number) => void;
}

function NumberInputField({
  label,
  value,
  disabled = false,
  min,
  max,
  step = 0.05,
  onCommit
}: NumberInputFieldProps) {
  const [draft, setDraft] = useState(formatEditableNumber(value));

  useEffect(() => {
    setDraft(formatEditableNumber(value));
  }, [value]);

  const commit = useCallback(() => {
    const parsed = Number.parseFloat(draft);
    if (!Number.isFinite(parsed)) {
      setDraft(formatEditableNumber(value));
      return;
    }
    const minClamped = min === undefined ? parsed : Math.max(min, parsed);
    const next = max === undefined ? minClamped : Math.min(max, minClamped);
    if (next !== value) {
      onCommit(next);
    } else {
      setDraft(formatEditableNumber(value));
    }
  }, [draft, max, min, onCommit, value]);

  return (
    <Field label={label}>
      <Input
        aria-label={label}
        disabled={disabled}
        type="number"
        min={min}
        max={max}
        step={step}
        value={draft}
        onBlur={commit}
        onChange={(_event, data) => setDraft(data.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.currentTarget.blur();
          }
        }}
      />
    </Field>
  );
}

export function RigEditorPage() {
  const stageHostRef = useRef<HTMLDivElement | null>(null);
  const adapterRef = useRef<RigStageAdapterHandle | null>(null);
  const [editor, dispatch] = useReducer(rigEditorReducer, createInitialEditorState());
  const [revision, setRevision] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState("Loaded sample project");
  const [selectedBoneId, setSelectedBoneId] = useState<string | null>(INITIAL_SELECTED_BONE_ID);
  const [selectedAttachmentId, setSelectedAttachmentId] = useState<string | null>(null);
  const [selectedTrackId, setSelectedTrackId] = useState<string | null>(null);
  const [selectedKeyframeId, setSelectedKeyframeId] = useState<string | null>(null);
  const [clipboardKeyframe, setClipboardKeyframe] = useState<Keyframe | null>(null);
  const [showLabels, setShowLabels] = useState(INITIAL_SHOW_LABELS);
  const [showDebugAxes, setShowDebugAxes] = useState(INITIAL_SHOW_DEBUG_AXES);
  const [editMode, setEditMode] = useState<RigEditMode>("setup");
  const [stretchEndpoint, setStretchEndpoint] = useState(true);
  const [reparentIssue, setReparentIssue] = useState<string | null>(null);
  const [playheadTime, setPlayheadTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [timelineZoom, setTimelineZoom] = useState(1);
  const [autokey, setAutokey] = useState(true);
  const [showOnionSkin, setShowOnionSkin] = useState(true);
  const [primitiveShape, setPrimitiveShape] = useState<"capsule" | "ellipse" | "rectangle">(
    "capsule"
  );
  const editorRef = useRef(editor);
  const playheadRef = useRef(playheadTime);
  const dragRef = useRef<{
    readonly startRig: RigDefinition;
    readonly startWorldPoint: { readonly x: number; readonly y: number };
    readonly mode: RigEditMode;
    readonly stretchEndpoint: boolean;
  } | null>(null);

  useEffect(() => {
    editorRef.current = editor;
  }, [editor]);

  useEffect(() => {
    playheadRef.current = playheadTime;
  }, [playheadTime]);

  const projectDocument = editor.document;
  const character = activeCharacter(projectDocument);
  const clip = activeClip(projectDocument);
  const actorId = actorIdForClip(projectDocument, character.id, clip);
  const showClipPose = (editMode === "animation" || isPlaying) && clip !== null && actorId !== null;
  const displayRig = showClipPose
    ? displayRigAtTime(character.rig, clip, actorId, playheadTime)
    : character.rig;
  const loopBounds = clip === null ? { start: 0, end: 0 } : clipLoopBounds(clip);
  const timelineWidth = clip === null ? 720 : Math.max(720, clip.duration * 360 * timelineZoom);
  const cameraBounds = useMemo(() => cameraBoundsFor(projectDocument), [projectDocument]);
  const childrenByParent = useMemo(() => buildChildrenByParent(character.rig.bones), [character.rig]);
  const endpoints = useMemo(() => computeBoneEndpoints(displayRig), [displayRig]);
  const worldTransforms = useMemo(() => computeWorldTransforms(displayRig), [displayRig]);
  const selectedSetupBone = character.rig.bones.find((bone) => bone.id === selectedBoneId) ?? null;
  const selectedDisplayBone = displayRig.bones.find((bone) => bone.id === selectedBoneId) ?? null;
  const selectedBone = selectedDisplayBone ?? selectedSetupBone;
  const selectedEndpoint = selectedBoneId === null ? undefined : endpoints.get(selectedBoneId);
  const selectedWorld = selectedBoneId === null ? undefined : worldTransforms.get(selectedBoneId);
  const selectedDescendants = useMemo(
    () =>
      selectedSetupBone === null
        ? new Set<string>()
        : getDescendantBoneIds(character.rig, selectedSetupBone.id),
    [character.rig, selectedSetupBone]
  );
  const selectedAttachment =
    character.attachments.find((attachment) => attachment.id === selectedAttachmentId) ?? null;
  const selectedTrack = clip?.tracks.find((track) => track.id === selectedTrackId) ?? null;
  const selectedKeyframe =
    selectedTrack?.keyframes.find((keyframe) => keyframe.id === selectedKeyframeId) ?? null;
  const canUndo = editor.history.undoStack.length > 0;
  const canRedo = editor.history.redoStack.length > 0;
  const seekPlayhead = useCallback(
    (time: number) => {
      const nextTime = clip === null ? 0 : clampClipTime(clip, time);
      playheadRef.current = nextTime;
      setPlayheadTime(nextTime);
    },
    [clip]
  );
  const createStageUpdate = useCallback(
    (time: number): RigStageUpdate => {
      const shouldShowClipPose =
        (editMode === "animation" || isPlaying) && clip !== null && actorId !== null;
      return {
        rig: shouldShowClipPose
          ? displayRigAtTime(character.rig, clip, actorId, time)
          : character.rig,
        attachments: character.attachments,
        onionSkins: shouldShowClipPose
          ? onionSkinRigs(character.rig, clip, actorId, time, showOnionSkin)
          : [],
        selectedBoneId,
        showLabels,
        showDebugAxes,
        cameraBounds
      };
    },
    [
      actorId,
      cameraBounds,
      character.attachments,
      character.rig,
      clip,
      editMode,
      isPlaying,
      selectedBoneId,
      showDebugAxes,
      showLabels,
      showOnionSkin
    ]
  );

  useEffect(() => {
    if (clip === null) {
      setSelectedTrackId(null);
      setSelectedKeyframeId(null);
      return;
    }
    if (selectedTrackId === null || !clip.tracks.some((track) => track.id === selectedTrackId)) {
      const firstTrack = clip.tracks[0] ?? null;
      setSelectedTrackId(firstTrack?.id ?? null);
      setSelectedKeyframeId(firstTrack?.keyframes[0]?.id ?? null);
    }
  }, [clip, selectedTrackId]);

  useEffect(() => {
    if (clip !== null) {
      setPlayheadTime((current) => {
        const nextTime = clampClipTime(clip, current);
        playheadRef.current = nextTime;
        return nextTime;
      });
    }
  }, [clip]);

  useEffect(() => {
    if (!isPlaying || clip === null) {
      return undefined;
    }
    let frame = 0;
    let previous = performance.now();
    let lastUiSync = previous;
    const tick = (now: number) => {
      const delta = ((now - previous) / 1000) * playbackSpeed;
      previous = now;
      const nextTime = advanceClipTime(clip, playheadRef.current, delta);
      playheadRef.current = nextTime;
      adapterRef.current?.updateRig(createStageUpdate(nextTime));
      if (now - lastUiSync >= 125) {
        lastUiSync = now;
        setPlayheadTime(nextTime);
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      setPlayheadTime(playheadRef.current);
    };
  }, [clip, createStageUpdate, isPlaying, playbackSpeed]);

  useEffect(() => {
    const pauseOnHidden = () => {
      if (globalThis.document.visibilityState === "hidden") {
        setIsPlaying(false);
      }
    };
    globalThis.document.addEventListener("visibilitychange", pauseOnHidden);
    return () => globalThis.document.removeEventListener("visibilitychange", pauseOnHidden);
  }, []);

  const runDocumentEdit = useCallback(
    (nextDocument: ProjectDocument, label: string, mergeKey?: string) => {
      if (nextDocument === editorRef.current.document) {
        return;
      }
      dispatch({
        type: "run",
        command: createDocumentCommand(nextDocument, label, mergeKey),
        mergeWithPrevious: mergeKey !== undefined
      });
    },
    []
  );

  const runRigEdit = useCallback(
    (nextRig: RigDefinition, label: string, mergeKey?: string) => {
      runDocumentEdit(replaceRig(editorRef.current.document, nextRig), label, mergeKey);
    },
    [runDocumentEdit]
  );

  const saveDocument = useCallback(async () => {
    setSaveStatus("Saving project...");
    try {
      const response =
        revision === null
          ? await createProject(editorRef.current.document)
          : await updateProject(
              editorRef.current.document.project.id,
              editorRef.current.document,
              revision
            );
      setRevision(response.revision);
      dispatch({ type: "load", document: response.document });
      setSaveStatus(`Saved revision ${response.revision}`);
    } catch (error) {
      setSaveStatus(error instanceof Error ? error.message : "Save failed");
    }
  }, [revision]);

  const reloadDocument = useCallback(async () => {
    if (revision === null) {
      dispatch({ type: "load", document: INITIAL_DOCUMENT });
      setSaveStatus("Reloaded sample project");
      return;
    }
    setSaveStatus("Reloading project...");
    try {
      const response = await getProject(editorRef.current.document.project.id);
      setRevision(response.revision);
      dispatch({ type: "load", document: response.document });
      setSaveStatus(`Reloaded revision ${response.revision}`);
    } catch (error) {
      setSaveStatus(error instanceof Error ? error.message : "Reload failed");
    }
  }, [revision]);

  const duplicateCurrentProject = useCallback(async () => {
    if (revision === null) {
      await saveDocument();
      return;
    }
    setSaveStatus("Duplicating project...");
    try {
      const response = await duplicateProject(editorRef.current.document.project.id);
      setRevision(response.revision);
      dispatch({ type: "load", document: response.document });
      setSaveStatus(`Duplicated as ${response.document.project.name}`);
    } catch (error) {
      setSaveStatus(error instanceof Error ? error.message : "Duplicate failed");
    }
  }, [revision, saveDocument]);

  useEffect(() => {
    if (!editor.dirty || revision === null) {
      return undefined;
    }
    const timeout = window.setTimeout(() => {
      void saveDocument();
    }, 800);
    return () => window.clearTimeout(timeout);
  }, [editor.dirty, editor.document, revision, saveDocument]);

  const handleStageBoneDrag = useCallback(
    (event: RigStageBoneDragEvent) => {
      if (event.phase === "start") {
        setSelectedBoneId(event.hit.boneId);
        setReparentIssue(null);
        dragRef.current = {
          startRig: activeCharacter(editorRef.current.document).rig,
          startWorldPoint: event.worldPoint,
          mode: editMode,
          stretchEndpoint
        };
        return;
      }

      const activeDrag = dragRef.current;
      if (activeDrag === null) {
        return;
      }
      if (event.phase === "cancel" || event.phase === "end") {
        dragRef.current = null;
        return;
      }

      const nextRig =
        event.hit.kind === "endpoint"
          ? editBoneEndpointToWorldPoint(activeDrag.startRig, event.hit.boneId, event.worldPoint, {
              mode: activeDrag.mode,
              allowLength: activeDrag.stretchEndpoint || event.shiftKey
            })
          : editBoneBodyByWorldDelta(
              activeDrag.startRig,
              event.hit.boneId,
              activeDrag.startWorldPoint,
              event.worldPoint,
              { mode: activeDrag.mode }
            );

      if (activeDrag.mode === "animation" && event.hit.kind === "endpoint") {
        const nextBone = nextRig.bones.find((bone) => bone.id === event.hit.boneId);
        const activeDocument = editorRef.current.document;
        const activeActorId = actorIdForClip(
          activeDocument,
          activeCharacter(activeDocument).id,
          activeClip(activeDocument)
        );
        if (nextBone !== undefined && activeActorId !== null && autokey) {
          runDocumentEdit(
            setBoneRotationKeyframe(
              activeDocument,
              activeActorId,
              event.hit.boneId,
              playheadTime,
              nextBone.setup_transform.rotation_deg
            ),
            "Capture drag pose",
            `drag-pose:${event.hit.boneId}`
          );
        }
        return;
      }

      runRigEdit(
        nextRig,
        event.hit.kind === "endpoint" ? "Drag bone endpoint" : "Drag bone body",
        `drag:${event.hit.boneId}:${event.hit.kind}`
      );
    },
    [autokey, editMode, playheadTime, runDocumentEdit, runRigEdit, stretchEndpoint]
  );
  const handleStageBoneDragRef = useRef(handleStageBoneDrag);

  useEffect(() => {
    handleStageBoneDragRef.current = handleStageBoneDrag;
  }, [handleStageBoneDrag]);

  useEffect(() => {
    const host = stageHostRef.current;
    if (host === null) {
      return;
    }
    let disposed = false;
    let adapter: RigStageAdapterHandle | null = null;
    let cleanupResize = () => {};

    const resize = () => {
      adapter?.resize(
        normalizeViewportSize(
          host.clientWidth || 640,
          host.clientHeight || 460,
          window.devicePixelRatio || 1
        )
      );
    };

    void import("../engine/renderer/RigStageAdapter").then(({ createRigStageAdapter }) => {
      if (disposed) {
        return;
      }
      adapter = createRigStageAdapter({
        host,
        onSelectBone: (boneId) => {
          setSelectedBoneId(boneId);
          setReparentIssue(null);
        },
        onDragBone: (event) => handleStageBoneDragRef.current(event)
      });
      adapterRef.current = adapter;
      const initialDocument = editorRef.current.document;
      const initialCharacter = activeCharacter(initialDocument);
      adapter.updateRig({
        rig: initialCharacter.rig,
        attachments: initialCharacter.attachments,
        selectedBoneId: INITIAL_SELECTED_BONE_ID,
        showLabels: INITIAL_SHOW_LABELS,
        showDebugAxes: INITIAL_SHOW_DEBUG_AXES,
        cameraBounds: cameraBoundsFor(initialDocument)
      });

      void adapter.mount().then(() => {
        if (disposed) {
          return;
        }
        resize();
        if ("ResizeObserver" in window) {
          const observer = new ResizeObserver(resize);
          observer.observe(host);
          cleanupResize = () => observer.disconnect();
        }
      });
    });

    return () => {
      disposed = true;
      cleanupResize();
      adapter?.destroy();
      adapterRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (isPlaying) {
      return;
    }
    adapterRef.current?.updateRig(createStageUpdate(playheadTime));
  }, [createStageUpdate, isPlaying, playheadTime]);

  const addPrimitiveToSelectedBone = useCallback(() => {
    if (selectedBoneId === null) {
      return;
    }
    const attachment = createPrimitiveAttachment({
      boneId: selectedBoneId,
      existingIds: new Set(character.attachments.map((candidate) => candidate.id)),
      shape: primitiveShape
    });
    const nextDocument = replaceAttachments(projectDocument, [...character.attachments, attachment]);
    setSelectedAttachmentId(attachment.id);
    runDocumentEdit(nextDocument, "Add primitive attachment");
  }, [character.attachments, primitiveShape, projectDocument, runDocumentEdit, selectedBoneId]);

  const updateSelectedAttachment = useCallback(
    (update: (attachment: AttachmentDefinition) => AttachmentDefinition, label: string) => {
      if (selectedAttachmentId === null) {
        return;
      }
      runDocumentEdit(
        replaceAttachments(
          projectDocument,
          updateAttachment(character.attachments, selectedAttachmentId, update)
        ),
        label
      );
    },
    [character.attachments, projectDocument, runDocumentEdit, selectedAttachmentId]
  );

  const importAttachmentFile = useCallback(
    async (file: File | null) => {
      if (file === null || selectedBoneId === null) {
        return;
      }
      try {
        const sha256 = await fileSha256Hex(file);
        const assetId = `asset_${sha256.slice(0, 16)}`;
        const isSvg = file.type === "image/svg+xml" || file.name.toLowerCase().endsWith(".svg");
        const isPng = file.type === "image/png" || file.name.toLowerCase().endsWith(".png");
        if (!isSvg && !isPng) {
          setSaveStatus("Only SVG and PNG attachments are supported");
          return;
        }
        if (isSvg) {
          sanitizeSvgMarkup(await readFileAsText(file));
        } else {
          const dataUrl = await readFileAsDataUrl(file);
          if (!isSafePngDataUrl(dataUrl)) {
            setSaveStatus("PNG import did not produce a safe data URL");
            return;
          }
        }
        const attachment: AttachmentDefinition = {
          id: createPrimitiveAttachment({
            boneId: selectedBoneId,
            existingIds: new Set(character.attachments.map((candidate) => candidate.id))
          }).id,
          bone_id: selectedBoneId,
          kind: isSvg ? "svg" : "png",
          asset_id: assetId,
          primitive: null,
          mesh: null,
          pivot: [0, 0],
          transform: { position: [0, 0], rotation_deg: 0, scale: [1, 1] },
          z_index: 0,
          visible: true
        };
        runDocumentEdit(
          {
            ...replaceAttachments(projectDocument, [...character.attachments, attachment]),
            asset_manifest: [
              ...projectDocument.asset_manifest.filter((asset) => asset.id !== assetId),
              {
                id: assetId,
                sha256,
                media_type: isSvg ? "image/svg+xml" : "image/png",
                display_name: file.name.replace(/[^a-zA-Z0-9_.-]+/g, "_")
              }
            ]
          },
          "Import attachment asset"
        );
        setSelectedAttachmentId(attachment.id);
        setSaveStatus(`Imported ${file.name}`);
      } catch (error) {
        setSaveStatus(error instanceof Error ? error.message : "Attachment import failed");
      }
    },
    [character.attachments, projectDocument, runDocumentEdit, selectedBoneId]
  );

  const captureSelectedBone = useCallback(() => {
    if (selectedBone === null || actorId === null) {
      return;
    }
    runDocumentEdit(
      setBoneRotationKeyframe(
        projectDocument,
        actorId,
        selectedBone.id,
        playheadTime,
        selectedBone.setup_transform.rotation_deg
      ),
      "Capture keyframe"
    );
  }, [actorId, playheadTime, projectDocument, runDocumentEdit, selectedBone]);

  const selectedTrackIsScalar =
    selectedTrack?.type === "bone_rotation" || selectedTrack?.type === "constraint_weight";
  const selectedCurvePoints =
    selectedTrack !== null && clip !== null ? scalarCurvePolyline(selectedTrack, clip.duration) : null;
  const selectedCurveValue =
    selectedTrack !== null ? scalarTrackValue(selectedTrack, playheadTime) : null;
  const selectedCurveVelocity =
    selectedTrack !== null && clip !== null
      ? scalarTrackVelocity(selectedTrack, playheadTime, clip.duration)
      : null;

  return (
    <section aria-label="Manual rig editor" className="rig-editor-layout">
      <div className="rig-editor-panel">
        <div className="section-heading">
          <div>
            <Title3 as="h2">Manual rig editor</Title3>
            <Body1 className="muted-text">{character.name}</Body1>
          </div>
          <div className="rig-heading-badges">
            {editor.dirty ? (
              <Badge appearance="tint" color="danger">
                Unsaved
              </Badge>
            ) : null}
            <Badge appearance="tint" color="brand">
              {character.rig.bones.length} bones
            </Badge>
            <Badge appearance="tint" color="success">
              {character.attachments.length} parts
            </Badge>
          </div>
        </div>

        <div className="rig-toolbar" aria-label="Rig viewport commands">
          <Tooltip content="Save project" relationship="label">
            <Button aria-label="Save project" icon={<Save size={18} />} onClick={saveDocument} />
          </Tooltip>
          <Button onClick={reloadDocument}>Reload</Button>
          <Button onClick={duplicateCurrentProject}>Duplicate</Button>
          <Tooltip content="Reset view" relationship="label">
            <Button
              aria-label="Reset view"
              icon={<Maximize2 size={18} />}
              onClick={() => adapterRef.current?.setCamera(DEFAULT_STAGE_CAMERA)}
            />
          </Tooltip>
          <Tooltip content="Undo" relationship="label">
            <Button
              aria-label="Undo"
              disabled={!canUndo}
              icon={<Undo2 size={18} />}
              onClick={() => dispatch({ type: "undo" })}
            />
          </Tooltip>
          <Tooltip content="Redo" relationship="label">
            <Button
              aria-label="Redo"
              disabled={!canRedo}
              icon={<Redo2 size={18} />}
              onClick={() => dispatch({ type: "redo" })}
            />
          </Tooltip>
          <RadioGroup
            aria-label="Rig edit mode"
            layout="horizontal"
            value={editMode}
            onChange={(_event, data) => {
              if (data.value === "setup" || data.value === "animation") {
                setEditMode(data.value);
              }
            }}
          >
            <Radio value="setup" label="Setup" />
            <Radio value="animation" label="Animate" />
          </RadioGroup>
          <Field>
            <Switch checked={showLabels} label="Labels" onChange={(_event, data) => setShowLabels(data.checked)} />
          </Field>
          <Field>
            <Switch checked={showDebugAxes} label="Axes" onChange={(_event, data) => setShowDebugAxes(data.checked)} />
          </Field>
          <Field>
            <Switch
              checked={stretchEndpoint}
              disabled={editMode !== "setup"}
              label="Stretch"
              onChange={(_event, data) => setStretchEndpoint(data.checked)}
            />
          </Field>
          <Field>
            <Switch checked={autokey} label="Autokey" onChange={(_event, data) => setAutokey(data.checked)} />
          </Field>
          <Field>
            <Switch
              checked={showOnionSkin}
              disabled={editMode !== "animation" && !isPlaying}
              label="Onion"
              onChange={(_event, data) => setShowOnionSkin(data.checked)}
            />
          </Field>
        </div>

        <div ref={stageHostRef} className="rig-stage-host" role="img" aria-label="Rig stage viewport" />

        <section className="timeline-panel" aria-label="Timeline editor">
          <div className="timeline-toolbar">
            <Tooltip content="Seek to loop start" relationship="label">
              <Button
                aria-label="Seek to loop start"
                icon={<SkipBack size={18} />}
                disabled={clip === null}
                onClick={() => seekPlayhead(loopBounds.start)}
              />
            </Tooltip>
            <Tooltip content={isPlaying ? "Pause" : "Play"} relationship="label">
              <Button
                aria-label={isPlaying ? "Pause" : "Play"}
                icon={isPlaying ? <Pause size={18} /> : <Play size={18} />}
                disabled={clip === null}
                onClick={() => setIsPlaying((current) => !current)}
              />
            </Tooltip>
            <Tooltip content="Seek to loop end" relationship="label">
              <Button
                aria-label="Seek to loop end"
                icon={<SkipForward size={18} />}
                disabled={clip === null}
                onClick={() => seekPlayhead(loopBounds.end)}
              />
            </Tooltip>
            <NumberInputField
              label="Playhead"
              value={playheadTime}
              min={0}
              max={clip?.duration ?? 0}
              step={0.01}
              onCommit={seekPlayhead}
            />
            <Field label="Ruler">
              <input
                aria-label="Timeline ruler"
                className="timeline-range"
                type="range"
                min={0}
                max={clip?.duration ?? 0}
                step={0.01}
                value={playheadTime}
                onChange={(event) => seekPlayhead(Number.parseFloat(event.target.value))}
              />
            </Field>
            <Field label="Zoom">
              <input
                aria-label="Timeline zoom"
                className="timeline-range timeline-zoom"
                type="range"
                min={1}
                max={6}
                step={0.5}
                value={timelineZoom}
                onChange={(event) => setTimelineZoom(Number.parseFloat(event.target.value))}
              />
            </Field>
            <Field label="Speed">
              <Select
                aria-label="Playback speed"
                value={String(playbackSpeed)}
                onChange={(event) => setPlaybackSpeed(Number.parseFloat(event.target.value))}
              >
                <option value="0.5">0.5x</option>
                <option value="1">1x</option>
                <option value="1.5">1.5x</option>
                <option value="2">2x</option>
              </Select>
            </Field>
            <Field>
              <Switch
                checked={clip?.loop ?? false}
                label="Loop"
                disabled={clip === null}
                onChange={(_event, data) => {
                  if (clip !== null) {
                    runDocumentEdit(
                      replaceClip(projectDocument, {
                        ...clip,
                        loop: data.checked,
                        loop_range: clip.loop_range ?? [0, clip.duration]
                      }),
                      "Edit loop"
                    );
                  }
                }}
              />
            </Field>
            <NumberInputField
              label="Loop start"
              value={loopBounds.start}
              disabled={clip === null}
              min={0}
              max={loopBounds.end}
              step={0.01}
              onCommit={(value) => {
                if (clip !== null) {
                  runDocumentEdit(
                    replaceClip(projectDocument, updateClipLoopRange(clip, { start: value })),
                    "Edit loop range"
                  );
                }
              }}
            />
            <NumberInputField
              label="Loop end"
              value={loopBounds.end}
              disabled={clip === null}
              min={loopBounds.start}
              max={clip?.duration ?? 0}
              step={0.01}
              onCommit={(value) => {
                if (clip !== null) {
                  runDocumentEdit(
                    replaceClip(projectDocument, updateClipLoopRange(clip, { end: value })),
                    "Edit loop range"
                  );
                }
              }}
            />
            <Button icon={<Plus size={17} />} disabled={selectedBone === null} onClick={captureSelectedBone}>
              Capture
            </Button>
            <Button
              icon={<Download size={17} />}
              disabled={clip === null}
              onClick={() => {
                if (clip !== null) {
                  downloadText(`${clip.id}.json`, exportClipJson(clip), "application/json");
                }
              }}
            >
              Clip JSON
            </Button>
            <Button
              icon={<Download size={17} />}
              disabled={clip === null || actorId === null}
              onClick={() => {
                if (clip !== null && actorId !== null) {
                  downloadText(
                    `${clip.id}.svg`,
                    exportRigidAnimatedSvg({ clip, character, actorId }),
                    "image/svg+xml"
                  );
                }
              }}
            >
              SVG
            </Button>
            <label className="file-button">
              <FileUp size={17} aria-hidden="true" />
              Import clip
              <input
                aria-label="Import clip JSON"
                type="file"
                accept="application/json,.json"
                onChange={async (event) => {
                  const file = event.currentTarget.files?.[0] ?? null;
                  if (file !== null) {
                    const imported = importClipJson(await readFileAsText(file));
                    runDocumentEdit(replaceClip(projectDocument, imported), "Import clip JSON");
                  }
                  event.currentTarget.value = "";
                }}
              />
            </label>
          </div>

          {clip === null ? (
            <Text className="muted-text">No clip is available.</Text>
          ) : (
            <div className="timeline-scroll" role="region" aria-label="Timeline tracks" tabIndex={0}>
              <div className="timeline-grid" style={{ width: `${timelineWidth}px` }}>
                {clip.tracks.map((track, trackIndex) => (
                  <div className="timeline-row" key={track.id}>
                    <button
                      type="button"
                      className="timeline-track-button"
                      aria-label={`Timeline track ${trackIndex + 1}`}
                      aria-pressed={track.id === selectedTrackId}
                      onClick={() => {
                        setSelectedTrackId(track.id);
                        setSelectedKeyframeId(track.keyframes[0]?.id ?? null);
                      }}
                    >
                      {trackLabel(track)}
                    </button>
                    <div className="timeline-lane">
                      {clip.loop ? (
                        <span
                          className="timeline-loop-range"
                          style={{
                            left: timelinePercent(loopBounds.start, clip.duration),
                            width: timelinePercent(loopBounds.end - loopBounds.start, clip.duration)
                          }}
                        />
                      ) : null}
                      {track.keyframes.map((keyframe, keyframeIndex) => (
                        <button
                          key={keyframe.id}
                          type="button"
                          className="timeline-keyframe"
                          aria-label={`Timeline keyframe ${trackIndex + 1}.${keyframeIndex + 1}`}
                          aria-pressed={keyframe.id === selectedKeyframeId}
                          style={{ left: timelinePercent(keyframe.time, clip.duration) }}
                          onClick={() => {
                            setSelectedTrackId(track.id);
                            setSelectedKeyframeId(keyframe.id);
                            seekPlayhead(keyframe.time);
                          }}
                        />
                      ))}
                      <span
                        className="timeline-playhead"
                        style={{ left: timelinePercent(playheadTime, clip.duration) }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>

      <aside className="rig-editor-side" aria-label="Rig editor details">
        <section className="rig-side-section" aria-label="Bone hierarchy">
          <div className="section-heading">
            <Text weight="semibold">Bone hierarchy</Text>
            <Crosshair size={17} aria-hidden="true" />
          </div>
          <BoneTree
            parentId={null}
            childrenByParent={childrenByParent}
            selectedBoneId={selectedBoneId}
            onSelectBone={(boneId) => {
              setSelectedBoneId(boneId);
              setReparentIssue(null);
            }}
          />
        </section>

        <section className="rig-side-section" aria-label="Selected bone inspector">
          <Text weight="semibold">Inspector</Text>
          {selectedBone === null || selectedSetupBone === null ? (
            <Text size={200} className="muted-text">
              No bone selected.
            </Text>
          ) : (
            <>
              <div className="bone-edit-grid">
                <NumberInputField
                  label="Local X"
                  value={selectedSetupBone.setup_transform.position[0]}
                  disabled={editMode !== "setup"}
                  onCommit={(value) =>
                    runRigEdit(
                      setBoneLocalPosition(character.rig, selectedSetupBone.id, [
                        value,
                        selectedSetupBone.setup_transform.position[1]
                      ]),
                      "Edit bone position"
                    )
                  }
                />
                <NumberInputField
                  label="Local Y"
                  value={selectedSetupBone.setup_transform.position[1]}
                  disabled={editMode !== "setup"}
                  onCommit={(value) =>
                    runRigEdit(
                      setBoneLocalPosition(character.rig, selectedSetupBone.id, [
                        selectedSetupBone.setup_transform.position[0],
                        value
                      ]),
                      "Edit bone position"
                    )
                  }
                />
                <NumberInputField
                  label="Rotation"
                  value={selectedBone.setup_transform.rotation_deg}
                  step={1}
                  onCommit={(value) => {
                    if (editMode === "animation" && actorId !== null && autokey) {
                      runDocumentEdit(
                        setBoneRotationKeyframe(
                          projectDocument,
                          actorId,
                          selectedSetupBone.id,
                          playheadTime,
                          value
                        ),
                        "Capture rotation key"
                      );
                    } else {
                      runRigEdit(setBoneLocalRotation(character.rig, selectedSetupBone.id, value), "Edit bone rotation");
                    }
                  }}
                />
                <NumberInputField
                  label="Length"
                  value={selectedSetupBone.length}
                  disabled={editMode !== "setup"}
                  min={0}
                  onCommit={(value) =>
                    runRigEdit(setBoneLength(character.rig, selectedSetupBone.id, value), "Edit bone length")
                  }
                />
                <Field label="Parent bone" className="bone-parent-field">
                  <Select
                    aria-label="Parent bone"
                    value={selectedSetupBone.parent_id ?? ""}
                    disabled={editMode !== "setup"}
                    onChange={(event) => {
                      const nextParentId = event.target.value === "" ? null : event.target.value;
                      const result = reparentBone(character.rig, selectedSetupBone.id, nextParentId);
                      if (result.changed) {
                        setReparentIssue(null);
                        runRigEdit(result.rig, "Reparent bone");
                      } else if (result.issues.length > 0) {
                        setReparentIssue(result.issues.map((issue) => issue.message).join(" "));
                      }
                    }}
                  >
                    <option value="" disabled={selectedSetupBone.parent_id !== null}>
                      none
                    </option>
                    {character.rig.bones
                      .filter((bone) => bone.id !== selectedSetupBone.id)
                      .map((bone) => (
                        <option
                          key={bone.id}
                          value={bone.id}
                          disabled={selectedDescendants.has(bone.id)}
                        >
                          {bone.id}
                        </option>
                      ))}
                  </Select>
                </Field>
              </div>
              {reparentIssue === null ? null : (
                <Text size={200} className="warning-text" role="alert">
                  {reparentIssue}
                </Text>
              )}
              <dl className="numeric-inspector">
                <div>
                  <dt>Bone</dt>
                  <dd>{selectedBone.id}</dd>
                </div>
                <div>
                  <dt>Parent</dt>
                  <dd>{selectedSetupBone.parent_id ?? "none"}</dd>
                </div>
                <div>
                  <dt>Local position</dt>
                  <dd>
                    {formatPair(
                      selectedSetupBone.setup_transform.position[0],
                      selectedSetupBone.setup_transform.position[1]
                    )}
                  </dd>
                </div>
                <div>
                  <dt>Local rotation</dt>
                  <dd>{formatNumber(selectedBone.setup_transform.rotation_deg)} deg</dd>
                </div>
                <div>
                  <dt>Length</dt>
                  <dd>{formatNumber(selectedSetupBone.length)}</dd>
                </div>
                <div>
                  <dt>World origin</dt>
                  <dd>
                    {selectedEndpoint === undefined
                      ? "unavailable"
                      : formatPair(selectedEndpoint.origin.x, selectedEndpoint.origin.y)}
                  </dd>
                </div>
                <div>
                  <dt>World tip</dt>
                  <dd>
                    {selectedEndpoint === undefined
                      ? "unavailable"
                      : formatPair(selectedEndpoint.tip.x, selectedEndpoint.tip.y)}
                  </dd>
                </div>
                <div>
                  <dt>World rotation</dt>
                  <dd>
                    {selectedWorld === undefined
                      ? "unavailable"
                      : `${formatNumber(rotationDegOf(selectedWorld))} deg`}
                  </dd>
                </div>
              </dl>
            </>
          )}
        </section>

        <section className="rig-side-section" aria-label="Attachment editor">
          <Text weight="semibold">Attachments</Text>
          <div className="attachment-toolbar">
            <Field label="Shape">
              <Select
                aria-label="Primitive shape"
                value={primitiveShape}
                onChange={(event) =>
                  setPrimitiveShape(event.target.value as "capsule" | "ellipse" | "rectangle")
                }
              >
                <option value="capsule">Capsule</option>
                <option value="ellipse">Ellipse</option>
                <option value="rectangle">Rectangle</option>
              </Select>
            </Field>
            <Button
              icon={<Plus size={17} />}
              disabled={selectedBoneId === null}
              onClick={addPrimitiveToSelectedBone}
            >
              Add
            </Button>
            <label className="file-button">
              <FileUp size={17} aria-hidden="true" />
              Asset
              <input
                aria-label="Import SVG or PNG attachment"
                type="file"
                accept="image/svg+xml,image/png,.svg,.png"
                onChange={(event) => {
                  void importAttachmentFile(event.currentTarget.files?.[0] ?? null);
                  event.currentTarget.value = "";
                }}
              />
            </label>
          </div>
          <div className="attachment-list">
            {character.attachments.map((attachment) => (
              <button
                type="button"
                className="attachment-row"
                key={attachment.id}
                aria-label={`Attachment ${attachment.id}`}
                aria-pressed={attachment.id === selectedAttachmentId}
                onClick={() => setSelectedAttachmentId(attachment.id)}
              >
                <span>{attachment.id}</span>
                <Caption1 aria-hidden="true">{attachment.bone_id}</Caption1>
              </button>
            ))}
          </div>
          {selectedAttachment === null ? null : (
            <div className="attachment-editor">
              <Field>
                <Switch
                  checked={selectedAttachment.visible}
                  label="Visible"
                  onChange={(_event, data) =>
                    updateSelectedAttachment(
                      (attachment) => ({ ...attachment, visible: data.checked }),
                      "Toggle attachment"
                    )
                  }
                />
              </Field>
              <NumberInputField
                label="Offset X"
                value={selectedAttachment.transform.position[0]}
                onCommit={(value) =>
                  updateSelectedAttachment(
                    (attachment) => ({
                      ...attachment,
                      transform: {
                        ...attachment.transform,
                        position: [value, attachment.transform.position[1]]
                      }
                    }),
                    "Edit attachment offset"
                  )
                }
              />
              <NumberInputField
                label="Offset Y"
                value={selectedAttachment.transform.position[1]}
                onCommit={(value) =>
                  updateSelectedAttachment(
                    (attachment) => ({
                      ...attachment,
                      transform: {
                        ...attachment.transform,
                        position: [attachment.transform.position[0], value]
                      }
                    }),
                    "Edit attachment offset"
                  )
                }
              />
              <NumberInputField
                label="Pivot X"
                value={selectedAttachment.pivot[0]}
                onCommit={(value) =>
                  updateSelectedAttachment(
                    (attachment) => ({ ...attachment, pivot: [value, attachment.pivot[1]] }),
                    "Edit attachment pivot"
                  )
                }
              />
              <NumberInputField
                label="Pivot Y"
                value={selectedAttachment.pivot[1]}
                onCommit={(value) =>
                  updateSelectedAttachment(
                    (attachment) => ({ ...attachment, pivot: [attachment.pivot[0], value] }),
                    "Edit attachment pivot"
                  )
                }
              />
              <NumberInputField
                label="Part rotation"
                value={selectedAttachment.transform.rotation_deg}
                step={1}
                onCommit={(value) =>
                  updateSelectedAttachment(
                    (attachment) => ({
                      ...attachment,
                      transform: { ...attachment.transform, rotation_deg: value }
                    }),
                    "Edit attachment rotation"
                  )
                }
              />
              <NumberInputField
                label="Scale X"
                value={selectedAttachment.transform.scale[0]}
                step={0.01}
                onCommit={(value) =>
                  updateSelectedAttachment(
                    (attachment) => ({
                      ...attachment,
                      transform: {
                        ...attachment.transform,
                        scale: [value, attachment.transform.scale[1]]
                      }
                    }),
                    "Edit attachment scale"
                  )
                }
              />
              <NumberInputField
                label="Scale Y"
                value={selectedAttachment.transform.scale[1]}
                step={0.01}
                onCommit={(value) =>
                  updateSelectedAttachment(
                    (attachment) => ({
                      ...attachment,
                      transform: {
                        ...attachment.transform,
                        scale: [attachment.transform.scale[0], value]
                      }
                    }),
                    "Edit attachment scale"
                  )
                }
              />
              <NumberInputField
                label="Z order"
                value={selectedAttachment.z_index}
                step={1}
                onCommit={(value) =>
                  updateSelectedAttachment(
                    (attachment) => ({ ...attachment, z_index: Math.round(value) }),
                    "Edit attachment z order"
                  )
                }
              />
            </div>
          )}
        </section>

        <section className="rig-side-section" aria-label="Keyframe inspector">
          <Text weight="semibold">Keyframe</Text>
          {selectedTrack === null || selectedKeyframe === null || clip === null ? (
            <Text size={200} className="muted-text">
              Select a keyframe.
            </Text>
          ) : (
            <div className="attachment-editor">
              <Text size={200}>{trackLabel(selectedTrack)}</Text>
              <Text size={200} className="muted-text">
                {selectedKeyframe.id}: {keyframeDisplayValue(selectedKeyframe)}
              </Text>
              {selectedCurvePoints === null ? null : (
                <div className="curve-preview" aria-label="Selected curve preview">
                  <svg viewBox="0 0 160 48" role="img" aria-label="Selected scalar curve">
                    <polyline points={selectedCurvePoints} />
                  </svg>
                  <Text size={200} className="muted-text">
                    value {selectedCurveValue === null ? "n/a" : formatNumber(selectedCurveValue)}
                    {" / "}
                    velocity{" "}
                    {selectedCurveVelocity === null ? "n/a" : formatNumber(selectedCurveVelocity)}
                  </Text>
                </div>
              )}
              <Field label="Interpolation">
                <Select
                  aria-label="Keyframe interpolation"
                  value={selectedKeyframe.interpolation}
                  onChange={(event) =>
                    runDocumentEdit(
                      updateSelectedKeyframe(
                        projectDocument,
                        selectedTrack.id,
                        selectedKeyframe.id,
                        (keyframe) => ({
                          ...keyframe,
                          interpolation: event.target.value as "stepped" | "linear" | "cubic"
                        })
                      ),
                      "Edit keyframe interpolation"
                    )
                  }
                >
                  <option value="stepped">Stepped</option>
                  <option value="linear">Linear</option>
                  <option value="cubic">Cubic</option>
                </Select>
              </Field>
              <NumberInputField
                label="Key time"
                value={selectedKeyframe.time}
                min={0}
                max={clip.duration}
                step={0.01}
                onCommit={(value) => {
                  runDocumentEdit(
                    replaceClip(
                      projectDocument,
                      moveKeyframe(clip, selectedTrack.id, selectedKeyframe.id, value)
                    ),
                    "Move keyframe"
                  );
                  seekPlayhead(value);
                }}
              />
              {selectedTrackIsScalar && typeof selectedKeyframe.value === "number" ? (
                <NumberInputField
                  label="Key value"
                  value={selectedKeyframe.value}
                  step={1}
                  onCommit={(value) =>
                    runDocumentEdit(
                      updateSelectedKeyframe(projectDocument, selectedTrack.id, selectedKeyframe.id, (keyframe) => ({
                        ...keyframe,
                        value
                      })),
                      "Edit keyframe value"
                    )
                  }
                />
              ) : Array.isArray(selectedKeyframe.value) ? (
                <>
                  <NumberInputField
                    label="Key X"
                    value={selectedKeyframe.value[0]}
                    onCommit={(value) =>
                      runDocumentEdit(
                        updateSelectedKeyframe(projectDocument, selectedTrack.id, selectedKeyframe.id, (keyframe) => ({
                          ...keyframe,
                          value: [value, Array.isArray(keyframe.value) ? keyframe.value[1] : 0]
                        })),
                        "Edit keyframe value"
                      )
                    }
                  />
                  <NumberInputField
                    label="Key Y"
                    value={selectedKeyframe.value[1]}
                    onCommit={(value) =>
                      runDocumentEdit(
                        updateSelectedKeyframe(projectDocument, selectedTrack.id, selectedKeyframe.id, (keyframe) => ({
                          ...keyframe,
                          value: [Array.isArray(keyframe.value) ? keyframe.value[0] : 0, value]
                        })),
                        "Edit keyframe value"
                      )
                    }
                  />
                </>
              ) : null}
              <div className="keyframe-actions">
                <Button
                  icon={<Copy size={17} />}
                  onClick={() => setClipboardKeyframe(selectedKeyframe)}
                >
                  Copy
                </Button>
                <Button
                  disabled={clipboardKeyframe === null}
                  onClick={() => {
                    if (clipboardKeyframe !== null) {
                      const pasted = {
                        ...clipboardKeyframe,
                        id: `${selectedTrack.id}_paste_${Math.round(playheadTime * 1000)}`,
                        time: playheadTime
                      };
                      const compatible =
                        Array.isArray(pasted.value) === Array.isArray(selectedKeyframe.value);
                      const tracks = compatible
                        ? (clip.tracks.map((track) =>
                            track.id === selectedTrack.id
                              ? {
                                  ...track,
                                  keyframes: [...track.keyframes, pasted].sort(
                                    (a, b) => a.time - b.time || a.id.localeCompare(b.id)
                                  )
                                }
                              : track
                          ) as AnimationClip["tracks"])
                        : clip.tracks;
                      runDocumentEdit(
                        replaceClip(projectDocument, { ...clip, tracks }),
                        "Paste keyframe"
                      );
                    }
                  }}
                >
                  Paste
                </Button>
                <Button
                  onClick={() =>
                    runDocumentEdit(
                      replaceClip(
                        projectDocument,
                        duplicateKeyframe(clip, selectedTrack.id, selectedKeyframe.id)
                      ),
                      "Duplicate keyframe"
                    )
                  }
                >
                  Duplicate
                </Button>
                <Button
                  icon={<Trash2 size={17} />}
                  onClick={() =>
                    runDocumentEdit(
                      replaceClip(
                        projectDocument,
                        deleteKeyframe(clip, selectedTrack.id, selectedKeyframe.id)
                      ),
                      "Delete keyframe"
                    )
                  }
                >
                  Delete
                </Button>
              </div>
            </div>
          )}
        </section>

        <Text size={200} className="muted-text">
          {saveStatus}
        </Text>
      </aside>
    </section>
  );
}
