import {
  Badge,
  Button,
  Caption1,
  Field,
  Input,
  Select,
  Slider,
  Spinner,
  Switch,
  Text,
  Textarea,
  Title2,
  Tooltip
} from "@fluentui/react-components";
import { useMutation, useQuery } from "@tanstack/react-query";
import { RotateCcw, Save, Sparkles, Wand2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  createProject,
  generateCharacter,
  getOllamaModels,
  pollJobUntilDone,
  type CharacterGenerationResult
} from "../api/client";
import {
  BUILDER_PRESETS,
  DEFAULT_CHARACTER_REQUEST,
  buildProceduralCharacter,
  characterBuilderRequestSchema,
  createGeneratedCharacterProjectDocument,
  regenerateCharacterRegion,
  type CharacterBuilderRegion,
  type CharacterBuilderRequest
} from "../engine/characterBuilder";
import type { RigStageAdapterHandle } from "../engine/renderer/RigStageAdapter";
import { normalizeViewportSize } from "../engine/renderer/viewport";
import { PROJECT_SCHEMA_VERSION, projectDocumentSchema, type CharacterDefinition } from "../schemas/project";

type SelectKey =
  | "presentation"
  | "age_category"
  | "height"
  | "build"
  | "hair_style"
  | "face_shape"
  | "top"
  | "bottom"
  | "footwear"
  | "outerwear"
  | "style";

type PaletteKey = keyof CharacterBuilderRequest["palette"];
type ProportionKey = keyof CharacterBuilderRequest["proportions"];

const PROPORTION_FIELDS: readonly {
  readonly key: ProportionKey;
  readonly label: string;
  readonly min: number;
  readonly max: number;
  readonly step: number;
}[] = [
  { key: "shoulder_width", label: "Shoulders", min: 0.75, max: 1.25, step: 0.01 },
  { key: "torso_length", label: "Torso", min: 0.82, max: 1.18, step: 0.01 },
  { key: "waist_width", label: "Waist", min: 0.72, max: 1.18, step: 0.01 },
  { key: "hip_width", label: "Hips", min: 0.75, max: 1.25, step: 0.01 },
  { key: "arm_length", label: "Arms", min: 0.84, max: 1.18, step: 0.01 },
  { key: "leg_length", label: "Legs", min: 0.84, max: 1.2, step: 0.01 },
  { key: "head_size", label: "Head", min: 0.86, max: 1.16, step: 0.01 },
  { key: "asymmetry", label: "Asymmetry", min: 0, max: 0.04, step: 0.001 }
];

function optionText(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function uniqueSaveToken(character: CharacterDefinition): string {
  const suffix = character.id.replace(/^char_proc_/, "").slice(0, 10);
  return `${suffix}_${Date.now().toString(36)}`;
}

function emptyAiProjectDocument(name: string) {
  const token = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
  return projectDocumentSchema.parse({
    asset_manifest: [],
    characters: [],
    clips: [],
    engine_version: "0.1.0",
    format: "rigstory-project",
    generation_records: [],
    motion_plans: [],
    project: { id: `project_ai_${token}`, name: `${name} (AI)` },
    scenes: [],
    schema_version: PROJECT_SCHEMA_VERSION
  });
}

interface GenerationCompare {
  readonly prevName: string;
  readonly prevBones: number;
  readonly newName: string;
  readonly newBones: number;
}

interface SelectFieldProps {
  readonly label: string;
  readonly value: string;
  readonly options: readonly string[];
  readonly onChange: (value: string) => void;
}

function SelectField({ label, value, options, onChange }: SelectFieldProps) {
  return (
    <Field label={label}>
      <Select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {optionText(option)}
          </option>
        ))}
      </Select>
    </Field>
  );
}

interface ProportionSliderProps {
  readonly label: string;
  readonly value: number;
  readonly min: number;
  readonly max: number;
  readonly step: number;
  readonly onChange: (value: number) => void;
}

function ProportionSlider({
  label,
  value,
  min,
  max,
  step,
  onChange
}: ProportionSliderProps) {
  return (
    <Field label={`${label} ${value.toFixed(step < 0.01 ? 3 : 2)}`}>
      <Slider
        aria-label={label}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(_event, data) => onChange(data.value)}
      />
    </Field>
  );
}

export function CharacterBuilderPage() {
  const stageHostRef = useRef<HTMLDivElement | null>(null);
  const adapterRef = useRef<RigStageAdapterHandle | null>(null);
  const [request, setRequest] = useState<CharacterBuilderRequest>(DEFAULT_CHARACTER_REQUEST);
  const [presetIndex, setPresetIndex] = useState("custom");
  const [region, setRegion] = useState<CharacterBuilderRegion>("hair");
  const [showLabels, setShowLabels] = useState(true);
  const [showDebugAxes, setShowDebugAxes] = useState(true);
  const [saveStatus, setSaveStatus] = useState("Unsaved");
  const [aiModel, setAiModel] = useState("");
  const [aiDescription, setAiDescription] = useState("");
  const [genResult, setGenResult] = useState<CharacterGenerationResult | null>(null);
  const [genError, setGenError] = useState<{ message: string; retryable: boolean } | null>(null);
  const [compare, setCompare] = useState<GenerationCompare | null>(null);
  const result = useMemo(() => buildProceduralCharacter(request), [request]);
  const [previewCharacter, setPreviewCharacter] = useState<CharacterDefinition>(result.character);
  const previewRef = useRef(previewCharacter);
  const overlayRef = useRef({ showDebugAxes, showLabels });

  useEffect(() => {
    setPreviewCharacter(result.character);
    setSaveStatus("Unsaved");
  }, [result.character]);

  useEffect(() => {
    previewRef.current = previewCharacter;
    overlayRef.current = { showDebugAxes, showLabels };
  }, [previewCharacter, showDebugAxes, showLabels]);

  useEffect(() => {
    const host = stageHostRef.current;
    if (host === null) {
      return undefined;
    }
    let disposed = false;
    let adapter: RigStageAdapterHandle | null = null;
    let observer: ResizeObserver | null = null;

    const resize = () => {
      adapter?.resize(
        normalizeViewportSize(
          host.clientWidth || 640,
          host.clientHeight || 480,
          window.devicePixelRatio || 1
        )
      );
    };

    void import("../engine/renderer/RigStageAdapter").then(({ createRigStageAdapter }) => {
      if (disposed) {
        return;
      }
      adapter = createRigStageAdapter({ host });
      adapterRef.current = adapter;
      void adapter.mount().then(() => {
        if (disposed) {
          return;
        }
        resize();
        const latestPreview = previewRef.current;
        const latestOverlay = overlayRef.current;
        adapter?.updateRig({
          rig: latestPreview.rig,
          attachments: latestPreview.attachments,
          selectedBoneId: null,
          showDebugAxes: latestOverlay.showDebugAxes,
          showLabels: latestOverlay.showLabels
        });
      });
      observer = new ResizeObserver(() => resize());
      observer.observe(host);
    });

    return () => {
      disposed = true;
      observer?.disconnect();
      adapter?.destroy();
      adapterRef.current = null;
    };
  }, []);

  useEffect(() => {
    adapterRef.current?.updateRig({
      rig: previewCharacter.rig,
      attachments: previewCharacter.attachments,
      selectedBoneId: null,
      showDebugAxes,
      showLabels
    });
  }, [previewCharacter, showDebugAxes, showLabels]);

  const patchRequest = useCallback((patch: Partial<CharacterBuilderRequest>) => {
    setPresetIndex("custom");
    setRequest((current) => characterBuilderRequestSchema.parse({ ...current, ...patch }));
  }, []);

  const patchSelect = useCallback(
    (key: SelectKey, value: string) => {
      patchRequest({ [key]: value } as Partial<CharacterBuilderRequest>);
    },
    [patchRequest]
  );

  const patchProportion = useCallback((key: ProportionKey, value: number) => {
    setPresetIndex("custom");
    setRequest((current) =>
      characterBuilderRequestSchema.parse({
        ...current,
        proportions: { ...current.proportions, [key]: value }
      })
    );
  }, []);

  const patchPalette = useCallback((key: PaletteKey, value: string) => {
    setPresetIndex("custom");
    setRequest((current) =>
      characterBuilderRequestSchema.parse({
        ...current,
        palette: { ...current.palette, [key]: value }
      })
    );
  }, []);

  const resetRequest = useCallback(() => {
    setPresetIndex("custom");
    setRequest(DEFAULT_CHARACTER_REQUEST);
  }, []);

  const applyPreset = useCallback((value: string) => {
    setPresetIndex(value);
    if (value === "custom") {
      return;
    }
    setRequest(BUILDER_PRESETS[Number.parseInt(value, 10)]);
  }, []);

  const regenerateRegion = useCallback(() => {
    setPreviewCharacter((current) => regenerateCharacterRegion(request, current, region));
    setSaveStatus("Unsaved");
  }, [region, request]);

  const saveCharacter = useCallback(async () => {
    setSaveStatus("Saving");
    try {
      const document = createGeneratedCharacterProjectDocument(
        previewCharacter,
        uniqueSaveToken(previewCharacter)
      );
      const saved = await createProject(document);
      setSaveStatus(`Saved ${saved.document.project.name}`);
    } catch {
      setSaveStatus("Save failed");
    }
  }, [previewCharacter]);

  const modelsQuery = useQuery({ queryKey: ["ollama-models"], queryFn: getOllamaModels });
  const models = useMemo(() => modelsQuery.data?.models ?? [], [modelsQuery.data]);

  useEffect(() => {
    if (aiModel === "" && models.length > 0) {
      setAiModel(models[0].name);
    }
  }, [aiModel, models]);

  const generateMutation = useMutation({
    mutationFn: async (): Promise<CharacterGenerationResult> => {
      const created = await createProject(emptyAiProjectDocument(request.name));
      const job = await generateCharacter(created.document.project.id, {
        model: aiModel,
        description: aiDescription,
        form: request,
        expected_revision: created.revision
      });
      const done = await pollJobUntilDone(job.id);
      if (done.state !== "succeeded" || done.result === null || done.result === undefined) {
        const failure = new Error(done.error ?? "Generation failed") as Error & {
          retryable?: boolean;
        };
        failure.retryable = done.retryable;
        throw failure;
      }
      return done.result as unknown as CharacterGenerationResult;
    },
    onSuccess: (generation) => {
      const nextRequest = characterBuilderRequestSchema.parse(generation.request);
      const nextCharacter = buildProceduralCharacter(nextRequest).character;
      setCompare({
        prevName: previewCharacter.name,
        prevBones: previewCharacter.rig.bones.length,
        newName: nextCharacter.name,
        newBones: nextCharacter.rig.bones.length
      });
      setPresetIndex("custom");
      setRequest(nextRequest);
      setGenResult(generation);
      setGenError(null);
      setSaveStatus(`Generated with ${generation.model_name}`);
    },
    onError: (error) => {
      const failure = error as Error & { retryable?: boolean };
      setGenError({ message: failure.message, retryable: Boolean(failure.retryable) });
      setGenResult(null);
    }
  });

  const canGenerate = aiModel !== "" && !generateMutation.isPending;

  return (
    <section className="builder-layout" aria-label="Character Builder">
      <div className="builder-main">
        <div className="section-heading">
          <div>
            <Title2 as="h2">Character Builder</Title2>
            <Text className="muted-text">{previewCharacter.name}</Text>
          </div>
          <div className="rig-heading-badges">
            <Badge appearance="tint" color="brand">
              {previewCharacter.rig.bones.length} bones
            </Badge>
            <Badge appearance="tint" color={result.diagnostics.length ? "warning" : "success"}>
              {result.diagnostics.length} issues
            </Badge>
          </div>
        </div>

        <div
          ref={stageHostRef}
          className="builder-stage-host"
          role="img"
          aria-label="Generated character preview"
        />

        <div className="builder-preview-toolbar">
          <Field>
            <Switch
              checked={showLabels}
              label="Labels"
              onChange={(_event, data) => setShowLabels(data.checked)}
            />
          </Field>
          <Field>
            <Switch
              checked={showDebugAxes}
              label="Axes"
              onChange={(_event, data) => setShowDebugAxes(data.checked)}
            />
          </Field>
          <SelectField
            label="Region"
            value={region}
            options={["hair", "face", "clothing"]}
            onChange={(value) => setRegion(value as CharacterBuilderRegion)}
          />
          <Tooltip content="Regenerate selected region" relationship="label">
            <Button icon={<Wand2 size={17} />} onClick={regenerateRegion}>
              Regenerate
            </Button>
          </Tooltip>
          <Button icon={<Save size={17} />} onClick={() => void saveCharacter()}>
            Save
          </Button>
          <Text size={200} className="muted-text">
            {saveStatus}
          </Text>
        </div>
      </div>

      <aside className="builder-controls" aria-label="Character request">
        <section className="rig-side-section" aria-label="AI generation">
          <div className="section-heading">
            <Text weight="semibold">AI generation</Text>
            <Badge
              appearance="tint"
              color={modelsQuery.data?.available ? "success" : "warning"}
            >
              {modelsQuery.data?.available ? `${models.length} models` : "No Ollama"}
            </Badge>
          </div>
          <div className="builder-control-grid">
            {models.length === 0 ? (
              <Caption1 className="muted-text">
                {modelsQuery.isLoading
                  ? "Checking for local Ollama models…"
                  : "No local models found. Start Ollama and pull a model, then reopen this tab."}
              </Caption1>
            ) : (
              <Field label="Model">
                <Select
                  aria-label="Generation model"
                  value={aiModel}
                  onChange={(event) => setAiModel(event.target.value)}
                >
                  {models.map((model) => (
                    <option key={model.name} value={model.name}>
                      {model.name}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            <Field label="Description">
              <Textarea
                aria-label="Character description"
                placeholder="e.g. a calm older shopkeeper in a green apron"
                value={aiDescription}
                resize="vertical"
                onChange={(_event, data) => setAiDescription(data.value)}
              />
            </Field>
          </div>
          <Button
            appearance="primary"
            icon={generateMutation.isPending ? <Spinner size="tiny" /> : <Sparkles size={17} />}
            disabled={!canGenerate}
            onClick={() => generateMutation.mutate()}
          >
            {generateMutation.isPending ? "Generating" : "Generate with AI"}
          </Button>

          {genError ? (
            <div className="builder-diagnostic-row" role="alert">
              <Badge appearance="tint" color="danger">
                {genError.retryable ? "Retryable" : "Failed"}
              </Badge>
              <Caption1>{genError.message}</Caption1>
            </div>
          ) : null}

          {genResult ? (
            <div className="ai-result" role="status">
              <Text size={200} weight="semibold">
                Blueprint · {genResult.blueprint.character_name}
              </Text>
              <Caption1 className="muted-text">
                {genResult.blueprint.presentation} · {genResult.blueprint.age_category} ·{" "}
                {genResult.blueprint.style.family} · {genResult.status}
              </Caption1>
              {genResult.warnings.length > 0 ? (
                <ul className="ai-warning-list">
                  {genResult.warnings.map((warning) => (
                    <li key={warning}>
                      <Caption1>{warning}</Caption1>
                    </li>
                  ))}
                </ul>
              ) : null}
              {compare ? (
                <Caption1 className="muted-text">
                  Previous: {compare.prevName} ({compare.prevBones} bones) → New:{" "}
                  {compare.newName} ({compare.newBones} bones)
                </Caption1>
              ) : null}
              <Text size={200} weight="semibold">
                Value provenance
              </Text>
              <div className="ai-provenance-list">
                {genResult.provenance.map((entry) => (
                  <div className="ai-provenance-row" key={entry.field}>
                    <Badge
                      appearance="tint"
                      color={
                        entry.source === "model"
                          ? "brand"
                          : entry.source === "derived"
                            ? "informative"
                            : "subtle"
                      }
                    >
                      {entry.source}
                    </Badge>
                    <Caption1>
                      {entry.field}: {String(entry.model_value)}
                    </Caption1>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </section>

        <section className="rig-side-section">
          <Text weight="semibold">Request</Text>
          <div className="builder-control-grid">
            <Field label="Preset">
              <Select
                aria-label="Preset"
                value={presetIndex}
                onChange={(event) => applyPreset(event.target.value)}
              >
                <option value="custom">Custom</option>
                {BUILDER_PRESETS.map((preset, index) => (
                  <option key={preset.name} value={index}>
                    {preset.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Name">
              <Input
                aria-label="Name"
                value={request.name}
                onChange={(_event, data) => patchRequest({ name: data.value })}
              />
            </Field>
            <SelectField
              label="Presentation"
              value={request.presentation}
              options={["neutral", "feminine", "masculine"]}
              onChange={(value) => patchSelect("presentation", value)}
            />
            <SelectField
              label="Age"
              value={request.age_category}
              options={["adult", "teen", "older_adult", "child"]}
              onChange={(value) => patchSelect("age_category", value)}
            />
            <SelectField
              label="Height"
              value={request.height}
              options={["average", "short", "tall"]}
              onChange={(value) => patchSelect("height", value)}
            />
            <SelectField
              label="Build"
              value={request.build}
              options={["average", "slender", "sturdy", "broad"]}
              onChange={(value) => patchSelect("build", value)}
            />
            <SelectField
              label="Hair"
              value={request.hair_style}
              options={["short", "bob", "curly", "long", "coily", "bald"]}
              onChange={(value) => patchSelect("hair_style", value)}
            />
            <SelectField
              label="Face"
              value={request.face_shape}
              options={["oval", "round", "square", "heart", "long"]}
              onChange={(value) => patchSelect("face_shape", value)}
            />
            <SelectField
              label="Top"
              value={request.top}
              options={["tshirt", "shirt", "sweater", "jacket"]}
              onChange={(value) => patchSelect("top", value)}
            />
            <SelectField
              label="Bottom"
              value={request.bottom}
              options={["trousers", "shorts", "skirt"]}
              onChange={(value) => patchSelect("bottom", value)}
            />
            <SelectField
              label="Footwear"
              value={request.footwear}
              options={["shoes", "sneakers", "boots"]}
              onChange={(value) => patchSelect("footwear", value)}
            />
            <SelectField
              label="Outerwear"
              value={request.outerwear}
              options={["none", "vest", "coat"]}
              onChange={(value) => patchSelect("outerwear", value)}
            />
            <SelectField
              label="Style"
              value={request.style}
              options={[
                "flat_vector",
                "cartoon",
                "graphic_novel",
                "paper_cutout",
                "silhouette"
              ]}
              onChange={(value) => patchSelect("style", value)}
            />
          </div>
          <Button icon={<RotateCcw size={17} />} onClick={resetRequest}>
            Reset
          </Button>
        </section>

        <section className="rig-side-section">
          <Text weight="semibold">Proportions</Text>
          <div className="builder-slider-grid">
            {PROPORTION_FIELDS.map((field) => (
              <ProportionSlider
                key={field.key}
                label={field.label}
                value={request.proportions[field.key]}
                min={field.min}
                max={field.max}
                step={field.step}
                onChange={(value) => patchProportion(field.key, value)}
              />
            ))}
          </div>
        </section>

        <section className="rig-side-section">
          <Text weight="semibold">Palette</Text>
          <div className="builder-palette-grid">
            {(["skin", "hair", "top", "bottom", "shoes", "accent"] as const).map((key) => (
              <Field label={optionText(key)} key={key}>
                <input
                  className="color-input"
                  aria-label={`${optionText(key)} color`}
                  type="color"
                  value={request.palette[key]}
                  onChange={(event) => patchPalette(key, event.currentTarget.value)}
                />
              </Field>
            ))}
          </div>
        </section>

        <section className="rig-side-section">
          <Text weight="semibold">Diagnostics</Text>
          <div className="builder-diagnostic-list">
            {result.diagnostics.length === 0 ? (
              <Caption1 className="muted-text">No diagnostics.</Caption1>
            ) : (
              result.diagnostics.map((diagnostic) => (
                <div className="builder-diagnostic-row" key={`${diagnostic.path}-${diagnostic.code}`}>
                  <Badge
                    appearance="tint"
                    color={diagnostic.severity === "error" ? "danger" : "warning"}
                  >
                    {diagnostic.code}
                  </Badge>
                  <Caption1>{diagnostic.message}</Caption1>
                </div>
              ))
            )}
          </div>
        </section>
      </aside>
    </section>
  );
}
