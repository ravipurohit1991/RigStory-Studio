import {
  Application,
  Container,
  Graphics,
  Text as PixiText
} from "pixi.js";

import { applyPoint, multiply, type Affine2, type Vec2 } from "../math";
import {
  computeBoneEndpoints,
  computeWorldTransforms,
  transformToAffine,
  type RigLike
} from "../rig";
import { skinMeshAttachment } from "../meshSkinning";
import type { AttachmentDefinition, PrimitiveAttachment } from "../../schemas/project";
import { hitTestRig, type RigHitTarget } from "./rigHitTest";
import {
  DEFAULT_CAMERA_BOUNDS,
  DEFAULT_STAGE_CAMERA,
  domainToScreen,
  normalizeViewportSize,
  panCameraByScreenDelta,
  pixelsPerWorldUnit,
  screenToDomain,
  visibleWorldBounds,
  wheelDeltaToZoom,
  worldBoundsToScreenRect,
  zoomCameraAtScreenPoint,
  type StageCamera,
  type ViewportSize,
  type WorldBounds
} from "./viewport";

export interface RigStageOptions {
  readonly host: HTMLElement;
  readonly onSelectBone?: (boneId: string | null, hit: RigHitTarget | null) => void;
  readonly onDragBone?: (event: RigStageBoneDragEvent) => void;
  readonly initialCamera?: StageCamera;
}

export type RigStageBoneDragPhase = "start" | "update" | "end" | "cancel";

export interface RigStageBoneDragEvent {
  readonly phase: RigStageBoneDragPhase;
  readonly hit: RigHitTarget;
  readonly screenPoint: { readonly x: number; readonly y: number };
  readonly worldPoint: { readonly x: number; readonly y: number };
  readonly shiftKey: boolean;
}

export interface RigStageUpdate {
  readonly rig: RigLike;
  readonly attachments?: readonly AttachmentDefinition[];
  readonly onionSkins?: readonly RigStageOnionSkin[];
  readonly selectedBoneId: string | null;
  readonly showLabels: boolean;
  readonly showDebugAxes: boolean;
  readonly cameraBounds?: WorldBounds;
}

export interface RigStageOnionSkin {
  readonly rig: RigLike;
  readonly alpha: number;
}

export interface RigStageAdapterHandle {
  mount(): Promise<void>;
  resize(viewport: ViewportSize): void;
  setCamera(camera: StageCamera): void;
  updateRig(update: RigStageUpdate): void;
  destroy(): void;
}

interface DragState {
  readonly pointerId: number;
  readonly startScreen: { readonly x: number; readonly y: number };
  readonly cameraStart: StageCamera;
  readonly hit: RigHitTarget | null;
  readonly isPanning: boolean;
  moved: boolean;
}

const STAGE_BACKGROUND = 0xf8fafc;
const GRID_MINOR = 0xd8dee6;
const GRID_MAJOR = 0xb8c2cc;
const AXIS_X = 0xb42318;
const AXIS_Y = 0x0e7c66;
const CAMERA_BOUNDS_COLOR = 0x806b00;
const BONE_COLOR = 0x355c7d;
const SELECTED_BONE_COLOR = 0xd1495b;
const JOINT_FILL = 0xfffbf0;
const JOINT_STROKE = 0x1f2937;
const ATTACHMENT_FALLBACK = 0xe6b17a;

function eventScreenPoint(event: PointerEvent | WheelEvent, canvas: HTMLCanvasElement) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top
  };
}

function chooseGridStep(camera: StageCamera): number {
  const targetWorldStep = 72 / pixelsPerWorldUnit(camera);
  const base = 10 ** Math.floor(Math.log10(targetWorldStep));
  for (const multiplier of [1, 2, 5, 10]) {
    const step = base * multiplier;
    if (step >= targetWorldStep) {
      return step;
    }
  }
  return base * 10;
}

function destroyLayerChildren(layer: Container): void {
  for (const child of layer.removeChildren()) {
    child.destroy();
  }
}

function colorNumber(hex: string | undefined): number {
  if (hex === undefined) {
    return ATTACHMENT_FALLBACK;
  }
  return Number.parseInt(hex.replace("#", ""), 16);
}

function inferredPrimitiveForBone(boneLength: number, attachmentId: string): PrimitiveAttachment {
  if (attachmentId.includes("head")) {
    return { shape: "ellipse", size: [0.42, 0.36], fill: "#f0c8a0", opacity: 1 };
  }
  if (attachmentId.includes("torso") || attachmentId.includes("pelvis")) {
    return { shape: "rectangle", size: [0.5, 0.34], fill: "#6b8fa8", opacity: 0.92 };
  }
  return {
    shape: "capsule",
    size: [Math.max(0.18, boneLength), 0.16],
    fill: "#e6b17a",
    opacity: 1
  };
}

function transformedPoint(
  matrix: Affine2,
  point: Vec2,
  camera: StageCamera,
  viewport: ViewportSize
) {
  return domainToScreen(applyPoint(matrix, point), camera, viewport);
}

export class PixiRigStageAdapter implements RigStageAdapterHandle {
  private readonly host: HTMLElement;
  private readonly onSelectBone?: (boneId: string | null, hit: RigHitTarget | null) => void;
  private readonly onDragBone?: (event: RigStageBoneDragEvent) => void;
  private app: Application | null = null;
  private viewport: ViewportSize;
  private camera: StageCamera;
  private update: RigStageUpdate | null = null;
  private drag: DragState | null = null;
  private readonly gridLayer = new Graphics();
  private readonly cameraBoundsLayer = new Graphics();
  private readonly attachmentLayer = new Graphics();
  private readonly onionLayer = new Graphics();
  private readonly boneLayer = new Graphics();
  private readonly debugLayer = new Graphics();
  private readonly labelLayer = new Container();

  constructor(options: RigStageOptions) {
    this.host = options.host;
    this.onSelectBone = options.onSelectBone;
    this.onDragBone = options.onDragBone;
    this.camera = options.initialCamera ?? DEFAULT_STAGE_CAMERA;
    this.viewport = normalizeViewportSize(
      this.host.clientWidth || 640,
      this.host.clientHeight || 480,
      window.devicePixelRatio || 1
    );
  }

  async mount(): Promise<void> {
    if (this.app !== null) {
      return;
    }
    const app = new Application();
    await app.init({
      autoDensity: true,
      antialias: true,
      backgroundColor: STAGE_BACKGROUND,
      height: this.viewport.height,
      resolution: this.viewport.devicePixelRatio,
      width: this.viewport.width
    });
    this.app = app;

    app.stage.addChild(this.gridLayer);
    app.stage.addChild(this.cameraBoundsLayer);
    app.stage.addChild(this.attachmentLayer);
    app.stage.addChild(this.onionLayer);
    app.stage.addChild(this.boneLayer);
    app.stage.addChild(this.debugLayer);
    app.stage.addChild(this.labelLayer);

    const canvas = app.canvas as HTMLCanvasElement;
    canvas.className = "rig-stage-canvas";
    canvas.addEventListener("wheel", this.handleWheel, { passive: false });
    canvas.addEventListener("pointerdown", this.handlePointerDown);
    canvas.addEventListener("pointermove", this.handlePointerMove);
    canvas.addEventListener("pointerup", this.handlePointerUp);
    canvas.addEventListener("pointercancel", this.handlePointerCancel);
    this.host.replaceChildren(canvas);
    this.render();
  }

  resize(viewport: ViewportSize): void {
    this.viewport = viewport;
    this.app?.renderer.resize(viewport.width, viewport.height, viewport.devicePixelRatio);
    this.render();
  }

  setCamera(camera: StageCamera): void {
    this.camera = camera;
    this.render();
  }

  updateRig(update: RigStageUpdate): void {
    this.update = update;
    this.render();
  }

  destroy(): void {
    const canvas = this.app?.canvas as HTMLCanvasElement | undefined;
    canvas?.removeEventListener("wheel", this.handleWheel);
    canvas?.removeEventListener("pointerdown", this.handlePointerDown);
    canvas?.removeEventListener("pointermove", this.handlePointerMove);
    canvas?.removeEventListener("pointerup", this.handlePointerUp);
    canvas?.removeEventListener("pointercancel", this.handlePointerCancel);
    this.drag = null;
    this.host.replaceChildren();
    this.app?.destroy({ removeView: true }, { children: true });
    this.app = null;
  }

  private readonly handleWheel = (event: WheelEvent): void => {
    if (this.app === null) {
      return;
    }
    event.preventDefault();
    const canvas = this.app.canvas as HTMLCanvasElement;
    const screenPoint = eventScreenPoint(event, canvas);
    this.camera = zoomCameraAtScreenPoint(
      this.camera,
      this.viewport,
      screenPoint,
      wheelDeltaToZoom(this.camera, event.deltaY)
    );
    this.render();
  };

  private readonly handlePointerDown = (event: PointerEvent): void => {
    if (this.app === null || this.update === null) {
      return;
    }
    const canvas = this.app.canvas as HTMLCanvasElement;
    const screenPoint = eventScreenPoint(event, canvas);
    const hit = hitTestRig(this.update.rig, screenPoint, this.camera, this.viewport);
    const isPanning = hit === null || event.button === 1 || event.altKey;
    this.drag = {
      pointerId: event.pointerId,
      startScreen: screenPoint,
      cameraStart: this.camera,
      hit,
      isPanning,
      moved: false
    };
    canvas.setPointerCapture(event.pointerId);
    if (!isPanning && hit !== null) {
      this.emitBoneDrag("start", hit, screenPoint, event.shiftKey);
    }
  };

  private readonly handlePointerMove = (event: PointerEvent): void => {
    if (this.drag === null || event.pointerId !== this.drag.pointerId) {
      return;
    }
    const canvas = event.currentTarget as HTMLCanvasElement;
    const screenPoint = eventScreenPoint(event, canvas);
    const delta = {
      x: screenPoint.x - this.drag.startScreen.x,
      y: screenPoint.y - this.drag.startScreen.y
    };
    this.drag.moved = this.drag.moved || Math.hypot(delta.x, delta.y) > 3;
    if (this.drag.isPanning) {
      this.camera = panCameraByScreenDelta(this.drag.cameraStart, delta, this.viewport);
      this.render();
    } else if (this.drag.hit !== null && this.drag.moved) {
      this.emitBoneDrag("update", this.drag.hit, screenPoint, event.shiftKey);
    }
  };

  private readonly handlePointerUp = (event: PointerEvent): void => {
    if (this.drag === null || event.pointerId !== this.drag.pointerId) {
      return;
    }
    const drag = this.drag;
    this.drag = null;
    const canvas = event.currentTarget as HTMLCanvasElement;
    const screenPoint = eventScreenPoint(event, canvas);
    canvas.releasePointerCapture(event.pointerId);
    if (!drag.moved) {
      this.onSelectBone?.(drag.hit?.boneId ?? null, drag.hit);
    } else if (!drag.isPanning && drag.hit !== null) {
      this.emitBoneDrag("end", drag.hit, screenPoint, event.shiftKey);
    }
  };

  private readonly handlePointerCancel = (event: PointerEvent): void => {
    if (this.drag?.pointerId === event.pointerId) {
      if (!this.drag.isPanning && this.drag.hit !== null && this.app !== null) {
        const canvas = this.app.canvas as HTMLCanvasElement;
        this.emitBoneDrag(
          "cancel",
          this.drag.hit,
          eventScreenPoint(event, canvas),
          event.shiftKey
        );
      }
      this.drag = null;
    }
  };

  private emitBoneDrag(
    phase: RigStageBoneDragPhase,
    hit: RigHitTarget,
    screenPoint: { readonly x: number; readonly y: number },
    shiftKey: boolean
  ): void {
    this.onDragBone?.({
      phase,
      hit,
      screenPoint,
      worldPoint: screenToDomain(screenPoint, this.camera, this.viewport),
      shiftKey
    });
  }

  private render(): void {
    this.drawGrid();
    this.drawCameraBounds();
    this.drawRig();
  }

  private drawGrid(): void {
    this.gridLayer.clear();
    const visible = visibleWorldBounds(this.camera, this.viewport);
    const [minX, minY, maxX, maxY] = visible;
    const step = chooseGridStep(this.camera);
    const startX = Math.floor(minX / step) * step;
    const endX = Math.ceil(maxX / step) * step;
    const startY = Math.floor(minY / step) * step;
    const endY = Math.ceil(maxY / step) * step;

    for (let x = startX; x <= endX + step / 2; x += step) {
      const a = domainToScreen({ x, y: minY }, this.camera, this.viewport);
      const b = domainToScreen({ x, y: maxY }, this.camera, this.viewport);
      const isMajor = Math.abs(Math.round(x / (step * 5)) - x / (step * 5)) < 1e-6;
      this.gridLayer.moveTo(a.x, a.y).lineTo(b.x, b.y).stroke({
        color: isMajor ? GRID_MAJOR : GRID_MINOR,
        width: isMajor ? 1.25 : 1,
        alpha: isMajor ? 0.85 : 0.55
      });
    }

    for (let y = startY; y <= endY + step / 2; y += step) {
      const a = domainToScreen({ x: minX, y }, this.camera, this.viewport);
      const b = domainToScreen({ x: maxX, y }, this.camera, this.viewport);
      const isMajor = Math.abs(Math.round(y / (step * 5)) - y / (step * 5)) < 1e-6;
      this.gridLayer.moveTo(a.x, a.y).lineTo(b.x, b.y).stroke({
        color: isMajor ? GRID_MAJOR : GRID_MINOR,
        width: isMajor ? 1.25 : 1,
        alpha: isMajor ? 0.85 : 0.55
      });
    }

    const xAxisStart = domainToScreen({ x: minX, y: 0 }, this.camera, this.viewport);
    const xAxisEnd = domainToScreen({ x: maxX, y: 0 }, this.camera, this.viewport);
    const yAxisStart = domainToScreen({ x: 0, y: minY }, this.camera, this.viewport);
    const yAxisEnd = domainToScreen({ x: 0, y: maxY }, this.camera, this.viewport);
    this.gridLayer.moveTo(xAxisStart.x, xAxisStart.y).lineTo(xAxisEnd.x, xAxisEnd.y).stroke({
      color: AXIS_X,
      width: 2,
      alpha: 0.75
    });
    this.gridLayer.moveTo(yAxisStart.x, yAxisStart.y).lineTo(yAxisEnd.x, yAxisEnd.y).stroke({
      color: AXIS_Y,
      width: 2,
      alpha: 0.75
    });
  }

  private drawCameraBounds(): void {
    this.cameraBoundsLayer.clear();
    const bounds = this.update?.cameraBounds ?? DEFAULT_CAMERA_BOUNDS;
    const rect = worldBoundsToScreenRect(bounds, this.camera, this.viewport);
    this.cameraBoundsLayer.rect(rect.x, rect.y, rect.width, rect.height).stroke({
      color: CAMERA_BOUNDS_COLOR,
      width: 2,
      alpha: 0.9
    });
  }

  private drawRig(): void {
    this.boneLayer.clear();
    this.attachmentLayer.clear();
    this.onionLayer.clear();
    this.debugLayer.clear();
    destroyLayerChildren(this.labelLayer);
    if (this.update === null) {
      return;
    }

    const {
      rig,
      attachments = [],
      onionSkins = [],
      selectedBoneId,
      showLabels,
      showDebugAxes
    } = this.update;
    const endpoints = computeBoneEndpoints(rig);

    this.drawAttachments(rig, attachments);
    this.drawOnionSkins(onionSkins);

    for (const bone of rig.bones) {
      const endpoint = endpoints.get(bone.id);
      if (endpoint === undefined) {
        continue;
      }
      const origin = domainToScreen(endpoint.origin, this.camera, this.viewport);
      const tip = domainToScreen(endpoint.tip, this.camera, this.viewport);
      const isSelected = bone.id === selectedBoneId;
      const color = isSelected ? SELECTED_BONE_COLOR : BONE_COLOR;

      if (bone.length > 0) {
        this.boneLayer.moveTo(origin.x, origin.y).lineTo(tip.x, tip.y).stroke({
          color,
          width: isSelected ? 6 : 4,
          alpha: 0.95,
          cap: "round"
        });
      }

      this.boneLayer.circle(origin.x, origin.y, isSelected ? 6 : 4).fill({ color: JOINT_FILL });
      this.boneLayer.circle(origin.x, origin.y, isSelected ? 6 : 4).stroke({
        color: isSelected ? SELECTED_BONE_COLOR : JOINT_STROKE,
        width: isSelected ? 2.5 : 1.5
      });

      if (bone.length > 0) {
        this.boneLayer.circle(tip.x, tip.y, isSelected ? 5 : 3.5).fill({ color });
      }

      if (showLabels) {
        const label = new PixiText({
          text: bone.id,
          style: {
            fill: 0x334155,
            fontFamily: "Inter, Segoe UI, sans-serif",
            fontSize: 11
          }
        });
        label.x = tip.x + 7;
        label.y = tip.y - 7;
        this.labelLayer.addChild(label);
      }
    }

    if (showDebugAxes) {
      this.drawDebugAxes(rig);
    }
  }

  private drawAttachments(
    rig: RigLike,
    attachments: readonly AttachmentDefinition[]
  ): void {
    if (attachments.length === 0) {
      return;
    }

    const worlds = computeWorldTransforms(rig);
    const bonesById = new Map(rig.bones.map((bone) => [bone.id, bone]));
    const sortedAttachments = [...attachments]
      .filter((attachment) => attachment.visible)
      .sort((a, b) => a.z_index - b.z_index || a.id.localeCompare(b.id));

    for (const attachment of sortedAttachments) {
      const boneWorld = worlds.get(attachment.bone_id);
      const bone = bonesById.get(attachment.bone_id);
      if (boneWorld === undefined || bone === undefined) {
        continue;
      }
      const primitive =
        attachment.primitive ?? inferredPrimitiveForBone(bone.length, attachment.id);
      const local = transformToAffine(attachment.transform);
      const matrix = multiply(boneWorld, local);
      if (attachment.kind === "mesh" && attachment.mesh !== null) {
        this.drawMeshAttachment(rig, attachment, matrix);
        continue;
      }
      this.drawPrimitiveAttachment(matrix, attachment.pivot, primitive);
    }
  }

  private drawMeshAttachment(
    rig: RigLike,
    attachment: AttachmentDefinition,
    matrix: Affine2
  ): void {
    if (attachment.mesh === null) {
      return;
    }
    const vertices = skinMeshAttachment(attachment, rig);
    const color = colorNumber(attachment.mesh.fill);
    const alpha = attachment.mesh.opacity;
    for (const triangle of attachment.mesh.triangles) {
      const points = triangle.indices.map((index) =>
        transformedPoint(matrix, vertices[index], this.camera, this.viewport)
      );
      this.attachmentLayer.poly(points).fill({ color, alpha });
    }
  }

  private drawPrimitiveAttachment(
    matrix: Affine2,
    pivot: readonly [number, number],
    primitive: PrimitiveAttachment
  ): void {
    const [width, height] = primitive.size;
    const left = -pivot[0];
    const right = width - pivot[0];
    const bottom = -height / 2 - pivot[1];
    const top = height / 2 - pivot[1];
    const color = colorNumber(primitive.fill);
    const alpha = primitive.opacity;

    if (primitive.shape === "ellipse") {
      const points = Array.from({ length: 24 }, (_value, index) => {
        const angle = (Math.PI * 2 * index) / 24;
        return transformedPoint(
          matrix,
          {
            x: left + width / 2 + Math.cos(angle) * (width / 2),
            y: Math.sin(angle) * (height / 2) - pivot[1]
          },
          this.camera,
          this.viewport
        );
      });
      this.attachmentLayer.poly(points).fill({ color, alpha });
      return;
    }

    const points =
      primitive.shape === "rectangle"
        ? [
            transformedPoint(matrix, { x: left, y: bottom }, this.camera, this.viewport),
            transformedPoint(matrix, { x: right, y: bottom }, this.camera, this.viewport),
            transformedPoint(matrix, { x: right, y: top }, this.camera, this.viewport),
            transformedPoint(matrix, { x: left, y: top }, this.camera, this.viewport)
          ]
        : Array.from({ length: 24 }, (_value, index) => {
            const radius = height / 2;
            const straight = Math.max(0, width - height);
            const angle =
              index < 12
                ? Math.PI / 2 - (Math.PI * index) / 11
                : -Math.PI / 2 - (Math.PI * (index - 12)) / 11;
            const centerX = index < 12 ? left + straight + radius : left + radius;
            return transformedPoint(
              matrix,
              { x: centerX + Math.cos(angle) * radius, y: Math.sin(angle) * radius - pivot[1] },
              this.camera,
              this.viewport
            );
          });

    this.attachmentLayer.poly(points).fill({ color, alpha });
  }

  private drawOnionSkins(onionSkins: readonly RigStageOnionSkin[]): void {
    for (const onionSkin of onionSkins) {
      const alpha = Math.min(Math.max(onionSkin.alpha, 0), 1);
      const endpoints = computeBoneEndpoints(onionSkin.rig);
      for (const bone of onionSkin.rig.bones) {
        const endpoint = endpoints.get(bone.id);
        if (endpoint === undefined) {
          continue;
        }
        const origin = domainToScreen(endpoint.origin, this.camera, this.viewport);
        const tip = domainToScreen(endpoint.tip, this.camera, this.viewport);
        if (bone.length > 0) {
          this.onionLayer.moveTo(origin.x, origin.y).lineTo(tip.x, tip.y).stroke({
            color: 0x6b7280,
            width: 2.5,
            alpha,
            cap: "round"
          });
        }
        this.onionLayer.circle(origin.x, origin.y, 3).fill({ color: 0x6b7280, alpha });
        if (bone.length > 0) {
          this.onionLayer.circle(tip.x, tip.y, 2.5).fill({ color: 0x6b7280, alpha });
        }
      }
    }
  }

  private drawDebugAxes(rig: RigLike): void {
    const worlds = computeWorldTransforms(rig);
    for (const matrix of worlds.values()) {
      const origin = applyPoint(matrix, { x: 0, y: 0 });
      const xAxis = applyPoint(matrix, { x: 0.18, y: 0 });
      const yAxis = applyPoint(matrix, { x: 0, y: 0.18 });
      const originScreen = domainToScreen(origin, this.camera, this.viewport);
      const xScreen = domainToScreen(xAxis, this.camera, this.viewport);
      const yScreen = domainToScreen(yAxis, this.camera, this.viewport);
      this.debugLayer.moveTo(originScreen.x, originScreen.y).lineTo(xScreen.x, xScreen.y).stroke({
        color: AXIS_X,
        width: 1.5,
        alpha: 0.85
      });
      this.debugLayer.moveTo(originScreen.x, originScreen.y).lineTo(yScreen.x, yScreen.y).stroke({
        color: AXIS_Y,
        width: 1.5,
        alpha: 0.85
      });
    }
  }
}

export function createRigStageAdapter(options: RigStageOptions): RigStageAdapterHandle {
  return new PixiRigStageAdapter(options);
}
