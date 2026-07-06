import { Badge, Button, Spinner, Text, Title2, Title3 } from "@fluentui/react-components";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Play } from "lucide-react";

import { compileDemoMotion, getProjects, getProject } from "../api/client";
import type { MotionAction } from "../api/client";

const DEMO_ACTIONS: MotionAction[] = [
  { id: "walk", type: "locomote", duration: 2, target: [2.2, 0], anchor_ref: null, amount: 1, hand: "right", repetitions: 1 },
  { id: "turn", type: "turn", duration: 0.6, target: [6, 1], anchor_ref: null, amount: 1, hand: "right", repetitions: 1 },
  { id: "sit", type: "sit", duration: 1, target: null, anchor_ref: "chair_main.seat", amount: 1, hand: "right", repetitions: 1 },
  { id: "wave", type: "wave", duration: 1.2, target: null, anchor_ref: null, amount: 0.7, hand: "right", repetitions: 2 }
];

export function MotionDevPage() {
  const projectsQuery = useQuery({ queryKey: ["projects"], queryFn: getProjects });
  const projectId = projectsQuery.data?.[0]?.id ?? null;
  const projectQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId ?? ""),
    enabled: projectId !== null
  });

  const scene = projectQuery.data?.document.scenes.find((candidate) =>
    candidate.objects.some((object) => object.id === "chair_main" || object.id === "chair_1")
  );
  const actor = scene?.actors[0];
  const characterId = actor?.character_id;

  const compileMutation = useMutation({
    mutationFn: () =>
      compileDemoMotion({
        scene_id: scene?.id ?? "",
        actor_id: actor?.id ?? "",
        character_id: characterId ?? "",
        clip_id: "clip_demo_walk_sit_wave",
        clip_name: "Walk, sit, wave",
        actions: DEMO_ACTIONS
      })
  });

  if (projectsQuery.isLoading || projectQuery.isLoading) {
    return (
      <section className="page-surface" aria-label="Motion">
        <Spinner label="Loading motion workspace" />
      </section>
    );
  }

  return (
    <section className="motion-dev-layout" aria-label="Motion">
      <div className="section-heading">
        <div>
          <Title2 as="h2">Deterministic Motion</Title2>
          <Text className="muted-text">Programmatic compiler, no model required</Text>
        </div>
        <Button
          appearance="primary"
          icon={<Play size={16} />}
          disabled={!scene || !actor || compileMutation.isPending}
          onClick={() => compileMutation.mutate()}
        >
          Compile
        </Button>
      </div>

      <div className="motion-action-list">
        {DEMO_ACTIONS.map((action) => (
          <article className="item-row" key={action.id}>
            <Text weight="semibold">{action.type}</Text>
            <Text size={200} className="muted-text">
              {action.id} · {action.duration}s
            </Text>
          </article>
        ))}
      </div>

      <aside className="motion-report">
        <Title3 as="h3">Report</Title3>
        {compileMutation.data ? (
          <>
            <Badge color={compileMutation.data.report.status === "ok" ? "success" : "warning"}>
              {compileMutation.data.report.status}
            </Badge>
            <Text>{compileMutation.data.clip.tracks.length} editable tracks</Text>
            <Text size={200} className="muted-text">
              max target error {compileMutation.data.report.metrics.max_target_error}
            </Text>
            <pre className="scene-snapshot-preview">
              {JSON.stringify(compileMutation.data.report, null, 2)}
            </pre>
          </>
        ) : (
          <Text className="muted-text">Compile the demo sequence to view metrics.</Text>
        )}
      </aside>
    </section>
  );
}
