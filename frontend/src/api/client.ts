import type { components } from "./generated/schema";
import type { ProjectDocument, SceneDefinition } from "../schemas/project";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "/api/v1").replace(/\/$/, "");

export type ComponentState = components["schemas"]["ComponentState"];

export type ComponentHealth = components["schemas"]["ComponentHealth"];

export type OllamaComponentHealth = components["schemas"]["OllamaComponentHealth"];

export type SystemHealth = components["schemas"]["SystemHealth"];

export interface ProjectSummary {
  readonly id: string;
  readonly name: string;
  readonly revision: string;
}

export interface ProjectRead {
  readonly document: ProjectDocument;
  readonly revision: string;
}

export type AppSettings = components["schemas"]["SettingsRead"];

export type ModelInfo = components["schemas"]["ModelInfo"];
export type OllamaModelsRead = components["schemas"]["OllamaModelsRead"];
export type OllamaTestResult = components["schemas"]["OllamaTestResult"];
export type Job = components["schemas"]["Job"];
export type JobState = components["schemas"]["JobState"];
export type BuilderDiagnostic = components["schemas"]["BuilderDiagnostic"];
export type CharacterBlueprint = components["schemas"]["CharacterBlueprint"];
export type CharacterBuilderRequestPayload = components["schemas"]["CharacterBuilderRequest"];
export type CharacterGenerationRequest = components["schemas"]["CharacterGenerationRequest"];
export type SceneSnapshotRead = components["schemas"]["SceneSnapshotRead"];
export type SceneValidationRead = components["schemas"]["SceneValidationRead"];
export type MotionAction = components["schemas"]["MotionAction"];
export type MotionCompileRead = components["schemas"]["MotionCompileRead"];
export type MotionPlan = components["schemas"]["MotionPlan"];
export type MotionPlanPatch = components["schemas"]["MotionPlanPatch"];
export type PlanWarning = components["schemas"]["PlanWarning"];
export type MotionPlanRead = components["schemas"]["MotionPlanRead"];
export type MotionPlanGenerationRequest = components["schemas"]["MotionPlanGenerationRequest"];
export type MotionPlanPatchRequest = components["schemas"]["MotionPlanPatchRequest"];
export type MotionPlanApplyPatchResult = components["schemas"]["MotionPlanApplyPatchResult"];
export type MotionValidationReport = components["schemas"]["MotionValidationReport"];
export type MediaExportRequest = components["schemas"]["MediaExportRequest"];

// Job result payloads (typed manually because a job result is carried as an
// opaque JsonValue in the generated OpenAPI schema).
export interface MotionPlanGenerationResult {
  readonly plan_id: string;
  readonly record_id: string;
  readonly revision: string;
  readonly status: "succeeded" | "repaired" | "failed";
  readonly model_name: string;
  readonly plan: MotionPlan;
}

export interface MotionPlanCompileResult {
  readonly plan_id: string;
  readonly clip_id: string;
  readonly revision: string;
  readonly engine_version: string;
  readonly report: MotionValidationReport;
}

export interface MotionPlanPatchResult {
  readonly plan_id: string;
  readonly record_id: string;
  readonly revision: string;
  readonly status: "succeeded" | "repaired" | "failed";
  readonly model_name: string;
  readonly patch: MotionPlanPatch;
  readonly patched_plan: MotionPlan;
  readonly diff: readonly string[];
}

export interface FieldProvenance {
  readonly field: string;
  readonly source: "model" | "derived" | "default";
  readonly model_value: string | number | boolean | null;
}

// The job result payload for a character generation (typed manually because it
// is carried as an opaque JsonValue in the generated OpenAPI schema).
export interface CharacterGenerationResult {
  readonly character_id: string;
  readonly record_id: string;
  readonly revision: string;
  readonly status: "succeeded" | "repaired" | "failed";
  readonly model_name: string;
  readonly blueprint: CharacterBlueprint;
  readonly request: CharacterBuilderRequestPayload;
  readonly provenance: readonly FieldProvenance[];
  readonly builder_diagnostics: readonly BuilderDiagnostic[];
  readonly warnings: readonly string[];
}

async function getJson<TResponse>(path: string): Promise<TResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`Request failed with HTTP ${response.status}`);
  }
  return (await response.json()) as TResponse;
}

async function sendJson<TResponse>(
  method: "POST" | "PATCH" | "DELETE",
  path: string,
  body?: unknown
): Promise<TResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!response.ok) {
    throw new Error(`Request failed with HTTP ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as TResponse;
  }
  return (await response.json()) as TResponse;
}

export function getHealth(): Promise<SystemHealth> {
  return getJson<SystemHealth>("/health");
}

export function getProjects(): Promise<ProjectSummary[]> {
  return getJson<ProjectSummary[]>("/projects");
}

export function createProject(document: ProjectDocument): Promise<ProjectRead> {
  return sendJson<ProjectRead>("POST", "/projects", { document });
}

export function getProject(projectId: string): Promise<ProjectRead> {
  return getJson<ProjectRead>(`/projects/${projectId}`);
}

export function updateProject(
  projectId: string,
  document: ProjectDocument,
  expectedRevision: string
): Promise<ProjectRead> {
  return sendJson<ProjectRead>("PATCH", `/projects/${projectId}`, {
    document,
    expected_revision: expectedRevision
  });
}

export function getProjectScenes(projectId: string): Promise<SceneDefinition[]> {
  return getJson<SceneDefinition[]>(`/projects/${projectId}/scenes`);
}

export function createScene(
  projectId: string,
  scene: SceneDefinition,
  expectedRevision: string
): Promise<ProjectRead> {
  return sendJson<ProjectRead>("POST", `/projects/${projectId}/scenes`, {
    scene,
    expected_revision: expectedRevision
  });
}

export function updateScene(
  scene: SceneDefinition,
  expectedRevision: string
): Promise<ProjectRead> {
  return sendJson<ProjectRead>("PATCH", `/scenes/${scene.id}`, {
    scene,
    expected_revision: expectedRevision
  });
}

export function getSceneSnapshot(sceneId: string): Promise<SceneSnapshotRead> {
  return getJson<SceneSnapshotRead>(`/scenes/${sceneId}/snapshot`);
}

export function validateScene(sceneId: string): Promise<SceneValidationRead> {
  return sendJson<SceneValidationRead>("POST", `/scenes/${sceneId}/validate`);
}

export function compileDemoMotion(request: {
  scene_id: string;
  actor_id: string;
  character_id: string;
  clip_id?: string;
  clip_name?: string;
  actions: MotionAction[];
}): Promise<MotionCompileRead> {
  return sendJson<MotionCompileRead>("POST", "/motion/demo/compile", request);
}

export function duplicateProject(projectId: string): Promise<ProjectRead> {
  return sendJson<ProjectRead>("POST", `/projects/${projectId}/duplicate`);
}

export function generateMotionPlan(
  sceneId: string,
  request: MotionPlanGenerationRequest
): Promise<Job> {
  return sendJson<Job>("POST", `/scenes/${sceneId}/motion-plans/generate`, request);
}

export function getMotionPlan(planId: string): Promise<MotionPlanRead> {
  return getJson<MotionPlanRead>(`/motion-plans/${planId}`);
}

export function updateMotionPlan(
  plan: MotionPlan,
  expectedRevision: string
): Promise<ProjectRead> {
  return sendJson<ProjectRead>("PATCH", `/motion-plans/${plan.id}`, {
    plan,
    expected_revision: expectedRevision
  });
}

export function compileMotionPlan(
  planId: string,
  expectedRevision: string,
  clipName?: string
): Promise<Job> {
  return sendJson<Job>("POST", `/motion-plans/${planId}/compile`, {
    expected_revision: expectedRevision,
    ...(clipName === undefined ? {} : { clip_name: clipName })
  });
}

export function requestMotionPlanPatch(
  planId: string,
  request: MotionPlanPatchRequest
): Promise<Job> {
  return sendJson<Job>("POST", `/motion-plans/${planId}/patch`, request);
}

export function applyMotionPlanPatch(
  planId: string,
  patch: MotionPlanPatch,
  expectedRevision: string
): Promise<MotionPlanApplyPatchResult> {
  return sendJson<MotionPlanApplyPatchResult>("POST", `/motion-plans/${planId}/apply-patch`, {
    patch,
    expected_revision: expectedRevision
  });
}

export function exportClipMedia(
  clipId: string,
  request: MediaExportRequest
): Promise<Job> {
  return sendJson<Job>("POST", `/clips/${clipId}/export`, request);
}

export function getSettings(): Promise<AppSettings> {
  return getJson<AppSettings>("/settings");
}

export function getOllamaModels(): Promise<OllamaModelsRead> {
  return getJson<OllamaModelsRead>("/ollama/models");
}

export function testOllamaModel(model: string, prompt?: string): Promise<OllamaTestResult> {
  return sendJson<OllamaTestResult>("POST", "/ollama/test", {
    model,
    ...(prompt === undefined ? {} : { prompt })
  });
}

export function generateCharacter(
  projectId: string,
  request: CharacterGenerationRequest
): Promise<Job> {
  return sendJson<Job>("POST", `/projects/${projectId}/characters/generate`, request);
}

export function getJob(jobId: string): Promise<Job> {
  return getJson<Job>(`/jobs/${jobId}`);
}

export function cancelJob(jobId: string): Promise<Job> {
  return sendJson<Job>("POST", `/jobs/${jobId}/cancel`);
}

const JOB_TERMINAL_STATES: ReadonlySet<JobState> = new Set([
  "succeeded",
  "failed",
  "cancelled"
]);

export function isTerminalJob(job: Job): boolean {
  return JOB_TERMINAL_STATES.has(job.state);
}

/** Poll a job until it reaches a terminal state or the attempt budget is spent. */
export async function pollJobUntilDone(
  jobId: string,
  { intervalMs = 800, maxAttempts = 240 }: { intervalMs?: number; maxAttempts?: number } = {}
): Promise<Job> {
  let job = await getJob(jobId);
  let attempts = 0;
  while (!isTerminalJob(job) && attempts < maxAttempts) {
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
    job = await getJob(jobId);
    attempts += 1;
  }
  return job;
}
