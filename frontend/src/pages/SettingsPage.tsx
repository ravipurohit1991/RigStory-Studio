import {
  Badge,
  Button,
  Caption1,
  Field,
  Input,
  Select,
  Spinner,
  Text,
  Title2
} from "@fluentui/react-components";
import { useMutation, useQuery } from "@tanstack/react-query";
import { PlugZap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  ComponentState,
  getHealth,
  getOllamaModels,
  getSettings,
  testOllamaModel
} from "../api/client";

function badgeColor(status: ComponentState): "success" | "warning" | "danger" | "important" {
  if (status === "healthy") {
    return "success";
  }
  if (status === "degraded" || status === "unavailable") {
    return "warning";
  }
  return "danger";
}

function OllamaModelsPanel() {
  const modelsQuery = useQuery({
    queryKey: ["ollama-models"],
    queryFn: getOllamaModels
  });
  const [selectedModel, setSelectedModel] = useState("");

  const models = useMemo(() => modelsQuery.data?.models ?? [], [modelsQuery.data]);
  useEffect(() => {
    if (selectedModel === "" && models.length > 0) {
      setSelectedModel(models[0].name);
    }
  }, [models, selectedModel]);

  const testMutation = useMutation({
    mutationFn: (model: string) => testOllamaModel(model)
  });

  return (
    <section className="rig-side-section" aria-label="Ollama models">
      <div className="section-heading">
        <Text weight="semibold">Local models</Text>
        <Badge
          appearance="tint"
          color={modelsQuery.data?.available ? "success" : "warning"}
        >
          {modelsQuery.data?.available ? `${models.length} installed` : "Unavailable"}
        </Badge>
      </div>

      {modelsQuery.isLoading ? (
        <Spinner size="tiny" label="Checking Ollama" />
      ) : models.length === 0 ? (
        <Caption1 className="muted-text">
          {modelsQuery.data?.detail ??
            "No installed models were found. Start Ollama and pull a model to enable AI generation."}
        </Caption1>
      ) : (
        <div className="settings-model-row">
          <Field label="Model">
            <Select
              aria-label="Ollama model"
              value={selectedModel}
              onChange={(event) => setSelectedModel(event.target.value)}
            >
              {models.map((model) => (
                <option key={model.name} value={model.name}>
                  {model.name}
                  {model.parameter_size ? ` · ${model.parameter_size}` : ""}
                </option>
              ))}
            </Select>
          </Field>
          <Button
            icon={<PlugZap size={17} />}
            disabled={selectedModel === "" || testMutation.isPending}
            onClick={() => testMutation.mutate(selectedModel)}
          >
            {testMutation.isPending ? "Testing" : "Test model"}
          </Button>
        </div>
      )}

      {testMutation.data ? (
        <div className="builder-diagnostic-row" role="status">
          <Badge appearance="tint" color={testMutation.data.ok ? "success" : "danger"}>
            {testMutation.data.ok ? "OK" : "Failed"}
          </Badge>
          <Caption1>
            {testMutation.data.detail}
            {testMutation.data.latency_ms != null
              ? ` (${Math.round(testMutation.data.latency_ms)} ms)`
              : ""}
          </Caption1>
        </div>
      ) : null}
      {testMutation.isError ? (
        <Caption1 role="alert">The model test request failed.</Caption1>
      ) : null}
    </section>
  );
}

export function SettingsPage() {
  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings
  });
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 30_000
  });

  if (settingsQuery.isLoading) {
    return (
      <section className="page-surface" aria-label="Settings">
        <Spinner label="Loading settings" />
      </section>
    );
  }

  if (settingsQuery.error || !settingsQuery.data) {
    return (
      <section className="page-surface" aria-label="Settings">
        <Title2 as="h2">Settings</Title2>
        <Text role="alert">Settings are unavailable.</Text>
      </section>
    );
  }

  const ollamaStatus = healthQuery.data?.ollama.status ?? "unavailable";

  return (
    <section className="page-surface" aria-label="Settings">
      <div className="section-heading">
        <Title2 as="h2">Settings</Title2>
        <Badge appearance="tint" color={badgeColor(ollamaStatus)}>
          Ollama {ollamaStatus}
        </Badge>
      </div>
      <div className="settings-grid">
        <Field label="Mode">
          <Input value={settingsQuery.data.environment} readOnly />
        </Field>
        <Field label="API base path">
          <Input value={settingsQuery.data.api_base_path} readOnly />
        </Field>
        <Field label="Asset store">
          <Input value={settingsQuery.data.asset_store_path} readOnly />
        </Field>
        <Field label="Ollama base URL">
          <Input value={settingsQuery.data.ollama_base_url} readOnly />
        </Field>
        <Field label="Generation timeout (s)">
          <Input
            value={String(settingsQuery.data.ollama_generation_timeout_seconds)}
            readOnly
          />
        </Field>
        <Field label="Keep alive">
          <Input value={settingsQuery.data.ollama_keep_alive} readOnly />
        </Field>
      </div>
      <Text size={200} className="muted-text">
        {healthQuery.data?.ollama.detail ?? "Ollama has not reported a healthy connection."}
      </Text>

      <OllamaModelsPanel />
    </section>
  );
}
