import { Badge, Button, Spinner, Text, Title2 } from "@fluentui/react-components";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { ComponentHealth, ComponentState, getHealth, OllamaComponentHealth } from "../api/client";

function badgeColor(status: ComponentState): "success" | "warning" | "danger" | "important" {
  if (status === "healthy") {
    return "success";
  }
  if (status === "degraded" || status === "unavailable") {
    return "warning";
  }
  return "danger";
}

interface HealthRowProps {
  label: string;
  health: ComponentHealth | OllamaComponentHealth;
}

function HealthRow({ label, health }: HealthRowProps) {
  const baseUrl = "base_url" in health ? health.base_url : null;
  return (
    <div className="health-row">
      <div>
        <Text weight="semibold">{label}</Text>
        <Text size={200} className="muted-text">
          {health.detail ?? "No detail reported."}
        </Text>
        {baseUrl ? (
          <Text size={200} className="muted-text">
            {baseUrl}
          </Text>
        ) : null}
      </div>
      <div className="health-status">
        <Badge appearance="tint" color={badgeColor(health.status)}>
          {health.status}
        </Badge>
        {health.latency_ms ? (
          <Text size={200} className="muted-text">
            {health.latency_ms} ms
          </Text>
        ) : null}
      </div>
    </div>
  );
}

export function HealthPage() {
  const { data: health, error, isLoading, refetch } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 30_000
  });

  if (isLoading) {
    return (
      <section className="page-surface" aria-label="Health">
        <Spinner label="Loading health" />
      </section>
    );
  }

  if (error || !health) {
    return (
      <section className="page-surface" aria-label="Health">
        <Title2 as="h2">Health</Title2>
        <Text role="alert">Health is unavailable.</Text>
      </section>
    );
  }

  return (
    <section className="page-surface" aria-label="Health">
      <div className="section-heading">
        <div>
          <Title2 as="h2">Health</Title2>
          <Text className="muted-text">Application status is reported separately from Ollama.</Text>
        </div>
        <Button icon={<RefreshCw size={16} />} onClick={() => void refetch()}>
          Refresh
        </Button>
      </div>
      <div className="health-list">
        <HealthRow label="Application" health={health.application} />
        <HealthRow label="Database" health={health.database} />
        <HealthRow label="Assets" health={health.assets} />
        <HealthRow label="Ollama" health={health.ollama} />
      </div>
    </section>
  );
}
