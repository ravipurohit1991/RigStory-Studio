import {
  Badge,
  Button,
  Field,
  Input,
  Spinner,
  Switch,
  Text,
  Textarea,
  Title2,
  Title3
} from "@fluentui/react-components";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, Play, Sparkles, Undo2, Wand2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  applyMotionPlanPatch,
  compileDemoMotion,
  compileMotionPlan,
  generateMotionPlan,
  getOllamaModels,
  getProject,
  getProjects,
  pollJobUntilDone,
  requestMotionPlanPatch,
  updateMotionPlan
} from "../api/client";
import type {
  Job,
  MotionAction,
  MotionPlan,
  MotionPlanCompileResult,
  MotionPlanGenerationResult,
  MotionPlanPatchResult
} from "../api/client";

const DEMO_ACTIONS: MotionAction[] = [
  { id: "walk", type: "locomote", duration: 2, target: [2.2, 0], anchor_ref: null, amount: 1, hand: "right", repetitions: 1 },
  { id: "turn", type: "turn", duration: 0.6, target: [6, 1], anchor_ref: null, amount: 1, hand: "right", repetitions: 1 },
  { id: "sit", type: "sit", duration: 1, target: null, anchor_ref: "chair_main.seat", amount: 1, hand: "right", repetitions: 1 },
  { id: "wave", type: "wave", duration: 1.2, target: null, anchor_ref: null, amount: 0.7, hand: "right", repetitions: 2 }
];

type PlanAction = MotionPlan["actions"][number];

interface PatchPreview {
  readonly result: MotionPlanPatchResult;
  readonly revision: string;
}

function actionTarget(action: PlanAction): string | null {
  const record = action as { target_ref?: string | null; partner_id?: string | null };
  return record.target_ref ?? record.partner_id ?? null;
}

async function runJob(job: Job): Promise<unknown> {
  const done = job.state === "succeeded" || job.state === "failed" || job.state === "cancelled"
    ? job
    : await pollJobUntilDone(job.id);
  if (done.state !== "succeeded" || done.result === null || done.result === undefined) {
    throw new Error(done.error ?? "The job did not succeed");
  }
  return done.result;
}

export function MotionPage() {
  const projectsQuery = useQuery({ queryKey: ["projects"], queryFn: getProjects });
  const projectId = projectsQuery.data?.[0]?.id ?? null;
  const projectQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId ?? ""),
    enabled: projectId !== null
  });
  const modelsQuery = useQuery({ queryKey: ["ollama-models"], queryFn: getOllamaModels });
  const models = useMemo(() => modelsQuery.data?.models ?? [], [modelsQuery.data]);

  const scene = useMemo(
    () => projectQuery.data?.document.scenes.find((candidate) => candidate.actors.length > 0),
    [projectQuery.data]
  );

  const [model, setModel] = useState("");
  const [useFixture, setUseFixture] = useState(false);
  const [prompt, setPrompt] = useState(
    "Mira walks to the chair, sits down, and waves with the right hand."
  );
  const [plan, setPlan] = useState<MotionPlan | null>(null);
  const [revision, setRevision] = useState<string | null>(null);
  const [previousPlan, setPreviousPlan] = useState<MotionPlan | null>(null);
  const [selectedActions, setSelectedActions] = useState<readonly string[]>([]);
  const [showJson, setShowJson] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [patchPreview, setPatchPreview] = useState<PatchPreview | null>(null);
  const [statusText, setStatusText] = useState("");

  useEffect(() => {
    if (model === "" && models.length > 0) {
      setModel(models[0].name);
    }
  }, [model, models]);
  useEffect(() => {
    if (revision === null && projectQuery.data) {
      setRevision(projectQuery.data.revision);
    }
  }, [projectQuery.data, revision]);

  const generateMutation = useMutation({
    mutationFn: async (): Promise<MotionPlanGenerationResult> => {
      const job = await generateMotionPlan(scene?.id ?? "", {
        model: model || "fixture",
        prompt,
        use_fixture: useFixture,
        expected_revision: revision ?? ""
      });
      return (await runJob(job)) as MotionPlanGenerationResult;
    },
    onSuccess: (result) => {
      setPlan(result.plan);
      setRevision(result.revision);
      setPreviousPlan(null);
      setPatchPreview(null);
      setSelectedActions([]);
      setStatusText(`Plan ${result.status} with ${result.model_name}`);
    },
    onError: (error) => setStatusText(error.message)
  });

  const savePlanMutation = useMutation({
    mutationFn: async (edited: MotionPlan) => updateMotionPlan(edited, revision ?? ""),
    onSuccess: (result, edited) => {
      setPlan(edited);
      setRevision(result.revision);
      setStatusText("Plan edits saved");
    },
    onError: (error) => setStatusText(error.message)
  });

  const compileMutation = useMutation({
    mutationFn: async (): Promise<MotionPlanCompileResult> => {
      const job = await compileMotionPlan(plan?.id ?? "", revision ?? "");
      return (await runJob(job)) as MotionPlanCompileResult;
    },
    onSuccess: (result) => {
      setRevision(result.revision);
      setStatusText(`Compiled clip ${result.clip_id}`);
    },
    onError: (error) => setStatusText(error.message)
  });

  const patchMutation = useMutation({
    mutationFn: async (): Promise<MotionPlanPatchResult> => {
      const job = await requestMotionPlanPatch(plan?.id ?? "", {
        model: model || "fixture",
        instruction,
        action_ids: [...selectedActions],
        expected_revision: revision ?? ""
      });
      return (await runJob(job)) as MotionPlanPatchResult;
    },
    onSuccess: (result) => {
      setPatchPreview({ result, revision: result.revision });
      setRevision(result.revision);
      setStatusText(`Correction ${result.status}; review the diff before applying`);
    },
    onError: (error) => setStatusText(error.message)
  });

  const applyPatchMutation = useMutation({
    mutationFn: async () =>
      applyMotionPlanPatch(
        plan?.id ?? "",
        patchPreview?.result.patch ?? { summary: "", operations: [], warnings: [] },
        revision ?? ""
      ),
    onSuccess: (result) => {
      setPreviousPlan(result.previous_plan);
      setPlan(result.plan);
      setRevision(result.document_revision);
      setPatchPreview(null);
      setStatusText("Patch applied; recompile to update the clip");
    },
    onError: (error) => setStatusText(error.message)
  });

  const undoPatchMutation = useMutation({
    mutationFn: async () => {
      if (previousPlan === null) {
        throw new Error("Nothing to undo");
      }
      return updateMotionPlan(previousPlan, revision ?? "");
    },
    onSuccess: (result) => {
      setPlan(previousPlan);
      setPreviousPlan(null);
      setRevision(result.revision);
      setStatusText("Patch undone");
    },
    onError: (error) => setStatusText(error.message)
  });

  const demoCompileMutation = useMutation({
    mutationFn: () =>
      compileDemoMotion({
        scene_id: scene?.id ?? "",
        actor_id: scene?.actors[0]?.id ?? "",
        character_id: scene?.actors[0]?.character_id ?? "",
        clip_id: "clip_demo_walk_sit_wave",
        clip_name: "Walk, sit, wave",
        actions: DEMO_ACTIONS
      })
  });

  const warningsByAction = useMemo(() => {
    const map = new Map<string, number>();
    for (const warning of plan?.warnings ?? []) {
      if (warning.action_id) {
        map.set(warning.action_id, (map.get(warning.action_id) ?? 0) + 1);
      }
    }
    return map;
  }, [plan]);

  const toggleActionSelection = (actionId: string) => {
    setSelectedActions((current) =>
      current.includes(actionId)
        ? current.filter((id) => id !== actionId)
        : [...current, actionId]
    );
  };

  const editActionDuration = (actionId: string, duration: number) => {
    if (plan === null || Number.isNaN(duration) || duration <= 0) {
      return;
    }
    setPlan({
      ...plan,
      actions: plan.actions.map((action) =>
        action.id === actionId ? { ...action, duration } : action
      )
    });
  };

  if (projectsQuery.isLoading || projectQuery.isLoading) {
    return (
      <section className="page-surface" aria-label="Motion">
        <Spinner label="Loading motion workspace" />
      </section>
    );
  }

  const busy =
    generateMutation.isPending ||
    compileMutation.isPending ||
    patchMutation.isPending ||
    applyPatchMutation.isPending;

  return (
    <section className="motion-dev-layout" aria-label="Motion">
      <div className="section-heading">
        <div>
          <Title2 as="h2">Motion</Title2>
          <Text className="muted-text">
            Describe the scenario; review and edit the plan; compile deterministically
          </Text>
        </div>
        <div className="rig-heading-badges">
          {scene ? (
            scene.actors.map((actor) => (
              <Badge key={actor.id} appearance="tint" color="brand">
                {actor.display_name}
              </Badge>
            ))
          ) : (
            <Badge appearance="tint" color="warning">
              No scene with actors
            </Badge>
          )}
        </div>
      </div>

      <div className="motion-plan-controls">
        <Field label="Scenario prompt">
          <Textarea
            value={prompt}
            resize="vertical"
            onChange={(_event, data) => setPrompt(data.value)}
          />
        </Field>
        <div className="builder-preview-toolbar">
          <Field label="Model">
            <select
              aria-label="Model"
              value={model}
              onChange={(event) => setModel(event.target.value)}
            >
              {models.length === 0 ? <option value="">No local models</option> : null}
              {models.map((entry) => (
                <option key={entry.name} value={entry.name}>
                  {entry.name}
                </option>
              ))}
            </select>
          </Field>
          <Field>
            <Switch
              checked={useFixture}
              label="Use fixture plan"
              onChange={(_event, data) => setUseFixture(data.checked)}
            />
          </Field>
          <Button
            appearance="primary"
            icon={<Sparkles size={16} />}
            disabled={!scene || busy || (model === "" && !useFixture)}
            onClick={() => generateMutation.mutate()}
          >
            Generate plan
          </Button>
          <Field>
            <Switch
              checked={showJson}
              label="Advanced JSON"
              onChange={(_event, data) => setShowJson(data.checked)}
            />
          </Field>
          <Text size={200} className="muted-text" aria-live="polite">
            {statusText}
          </Text>
        </div>
      </div>

      {plan ? (
        <div className="motion-plan-preview">
          <Title3 as="h3">{plan.summary}</Title3>
          {plan.warnings.length > 0 ? (
            <div className="rig-heading-badges" role="list" aria-label="Plan warnings">
              {plan.warnings.map((warning, index) => (
                <Badge key={index} appearance="tint" color="warning" role="listitem">
                  {warning.code}
                </Badge>
              ))}
            </div>
          ) : null}
          <div className="motion-action-list" role="list" aria-label="Planned actions">
            {plan.actions.map((action) => (
              <article
                className="item-row"
                key={action.id}
                role="listitem"
                aria-selected={selectedActions.includes(action.id)}
              >
                <Button
                  appearance={selectedActions.includes(action.id) ? "primary" : "secondary"}
                  size="small"
                  aria-pressed={selectedActions.includes(action.id)}
                  onClick={() => toggleActionSelection(action.id)}
                >
                  {action.id}
                </Button>
                <Text weight="semibold">{action.type}</Text>
                <Badge appearance="outline">{action.actor_id}</Badge>
                {actionTarget(action) ? (
                  <Text size={200} className="muted-text">
                    → {actionTarget(action)}
                  </Text>
                ) : null}
                {action.starts_after.length > 0 ? (
                  <Text size={200} className="muted-text">
                    after {action.starts_after.join(", ")}
                  </Text>
                ) : null}
                <Field label={`Duration of ${action.id}`} size="small">
                  <Input
                    type="number"
                    size="small"
                    step={0.1}
                    min={0.1}
                    value={String(action.duration)}
                    onChange={(_event, data) =>
                      editActionDuration(action.id, Number.parseFloat(data.value))
                    }
                  />
                </Field>
                {warningsByAction.get(action.id) ? (
                  <Badge appearance="tint" color="warning">
                    {warningsByAction.get(action.id)} warning(s)
                  </Badge>
                ) : null}
              </article>
            ))}
          </div>
          {plan.sync.length > 0 ? (
            <Text size={200} className="muted-text">
              Synchronization: {plan.sync.map((entry) => `${entry.kind}(${entry.action_ids.join(", ")})`).join("; ")}
            </Text>
          ) : null}
          <div className="builder-preview-toolbar">
            <Button
              icon={<Check size={16} />}
              disabled={busy || savePlanMutation.isPending}
              onClick={() => savePlanMutation.mutate(plan)}
            >
              Save plan edits
            </Button>
            <Button
              appearance="primary"
              icon={<Play size={16} />}
              disabled={busy}
              onClick={() => compileMutation.mutate()}
            >
              Approve and compile
            </Button>
          </div>
          {showJson ? (
            <pre className="scene-snapshot-preview" aria-label="Plan JSON">
              {JSON.stringify(plan, null, 2)}
            </pre>
          ) : null}

          <div className="motion-plan-correction">
            <Title3 as="h3">Correction</Title3>
            <Field label="Correction prompt (scoped to the selected actions)">
              <Textarea
                value={instruction}
                resize="vertical"
                onChange={(_event, data) => setInstruction(data.value)}
              />
            </Field>
            <div className="builder-preview-toolbar">
              <Button
                icon={<Wand2 size={16} />}
                disabled={busy || instruction.trim() === "" || (model === "" && !useFixture)}
                onClick={() => patchMutation.mutate()}
              >
                Request correction
              </Button>
              {previousPlan ? (
                <Button
                  icon={<Undo2 size={16} />}
                  disabled={busy || undoPatchMutation.isPending}
                  onClick={() => undoPatchMutation.mutate()}
                >
                  Undo patch
                </Button>
              ) : null}
            </div>
            {patchPreview ? (
              <div className="motion-patch-preview">
                <Text weight="semibold">{patchPreview.result.patch.summary}</Text>
                <ul aria-label="Patch diff">
                  {patchPreview.result.diff.map((line, index) => (
                    <li key={index}>
                      <Text size={200}>{line}</Text>
                    </li>
                  ))}
                </ul>
                <div className="builder-preview-toolbar">
                  <Button
                    appearance="primary"
                    disabled={applyPatchMutation.isPending}
                    onClick={() => applyPatchMutation.mutate()}
                  >
                    Apply patch
                  </Button>
                  <Button onClick={() => setPatchPreview(null)}>Discard</Button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <Text className="muted-text">
          Generate a plan to review its actions before compiling.
        </Text>
      )}

      <aside className="motion-report">
        <Title3 as="h3">Report</Title3>
        {compileMutation.data ? (
          <>
            <Badge
              color={compileMutation.data.report.status === "ok" ? "success" : "warning"}
            >
              {compileMutation.data.report.status}
            </Badge>
            <Text>clip {compileMutation.data.clip_id}</Text>
            <Text size={200} className="muted-text">
              engine {compileMutation.data.engine_version} · max target error{" "}
              {compileMutation.data.report.metrics.max_target_error}
            </Text>
            <pre className="scene-snapshot-preview">
              {JSON.stringify(compileMutation.data.report, null, 2)}
            </pre>
          </>
        ) : (
          <Text className="muted-text">Compile a plan to view its validation report.</Text>
        )}

        <Title3 as="h3">Deterministic demo</Title3>
        <Text size={200} className="muted-text">
          Deterministic compiler without a plan or model
        </Text>
        <Button
          icon={<Play size={16} />}
          disabled={!scene || demoCompileMutation.isPending}
          onClick={() => demoCompileMutation.mutate()}
        >
          Compile demo
        </Button>
        {demoCompileMutation.data ? (
          <Text size={200} className="muted-text">
            {demoCompileMutation.data.clip.tracks.length} editable tracks · max target error{" "}
            {demoCompileMutation.data.report.metrics.max_target_error}
          </Text>
        ) : null}
      </aside>
    </section>
  );
}
