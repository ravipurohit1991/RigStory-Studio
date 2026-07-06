import {
  Badge,
  Button,
  Spinner,
  Text,
  Title2,
  Title3
} from "@fluentui/react-components";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, Plus } from "lucide-react";
import { useMemo, useState } from "react";

import {
  createScene,
  getProject,
  getProjects,
  getSceneSnapshot,
  validateScene
} from "../api/client";
import type { ProjectRead } from "../api/client";
import type { SceneDefinition } from "../schemas/project";

function roomScene(project: ProjectRead): SceneDefinition {
  const characters = project.document.characters;
  const first = characters[0]?.id ?? "char_missing_alpha";
  const second = characters[1]?.id ?? first;
  return {
    id: "scene_demo_room",
    name: "Demo Room",
    world_bounds: [-5, -1, 7, 5],
    ground_y: 0,
    actors: [
      {
        id: "actor_mira",
        character_id: first,
        display_name: "Mira",
        root_transform: { position: [-3.5, 0], rotation_deg: 0, scale: [1, 1] },
        facing: "right",
        state: "standing"
      },
      {
        id: "actor_jon",
        character_id: second,
        display_name: "Jon",
        root_transform: { position: [4.5, 0], rotation_deg: 0, scale: [1, 1] },
        facing: "left",
        state: "standing"
      }
    ],
    objects: [
      {
        id: "floor_main",
        name: "Floor",
        kind: "floor",
        transform: { position: [0, 0], rotation_deg: 0, scale: [1, 1] },
        bounds: [-5, -0.25, 7, 0],
        visual: { type: "rectangle", fill: "#d8dee9", opacity: 1 },
        colliders: [{ type: "box", center: [1, -0.125], size: [12, 0.25], rotation_deg: 0 }],
        anchors: [],
        affordances: [],
        collision_layer: "ground",
        collision_mask: ["default"],
        body_type: "static",
        visible: true,
        locked: false,
        walkable: true,
        blocked: false
      },
      {
        id: "chair_main",
        name: "Chair",
        kind: "chair",
        transform: { position: [0, 0], rotation_deg: 0, scale: [1, 1] },
        bounds: [2, 0, 3, 1.4],
        visual: { type: "rectangle", fill: "#b7c7a3", opacity: 1 },
        colliders: [{ type: "box", center: [2.5, 0.45], size: [1, 0.9], rotation_deg: 0 }],
        anchors: [
          { id: "seat", position: [2.5, 0.55], rotation_deg: 0 },
          { id: "back", position: [2.85, 1.1], rotation_deg: 0 }
        ],
        affordances: [
          { type: "sit", anchor_id: "seat" },
          { type: "lean", anchor_id: "back" }
        ],
        collision_layer: "default",
        collision_mask: ["default"],
        body_type: "static",
        visible: true,
        locked: false,
        walkable: false,
        blocked: false
      },
      {
        id: "door_main",
        name: "Door",
        kind: "door",
        transform: { position: [0, 0], rotation_deg: 0, scale: [1, 1] },
        bounds: [5.6, 0, 6, 2.2],
        visual: { type: "rectangle", fill: "#8d99ae", opacity: 1 },
        colliders: [{ type: "box", center: [5.8, 1.1], size: [0.4, 2.2], rotation_deg: 0 }],
        anchors: [{ id: "handle", position: [5.65, 1.05], rotation_deg: 0 }],
        affordances: [
          { type: "grasp", anchor_id: "handle" },
          { type: "look_at", anchor_id: null }
        ],
        collision_layer: "default",
        collision_mask: ["default"],
        body_type: "static",
        visible: true,
        locked: false,
        walkable: false,
        blocked: false
      }
    ]
  };
}

export function SceneEditorPage() {
  const queryClient = useQueryClient();
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null);

  const projectsQuery = useQuery({ queryKey: ["projects"], queryFn: getProjects });
  const activeProjectId = selectedProjectId ?? projectsQuery.data?.[0]?.id ?? null;
  const projectQuery = useQuery({
    queryKey: ["project", activeProjectId],
    queryFn: () => getProject(activeProjectId ?? ""),
    enabled: activeProjectId !== null
  });
  const scenes = useMemo(() => projectQuery.data?.document.scenes ?? [], [projectQuery.data]);
  const activeSceneId = selectedSceneId ?? scenes[0]?.id ?? null;

  const snapshotQuery = useQuery({
    queryKey: ["sceneSnapshot", activeSceneId],
    queryFn: () => getSceneSnapshot(activeSceneId ?? ""),
    enabled: activeSceneId !== null
  });
  const validationQuery = useQuery({
    queryKey: ["sceneValidation", activeSceneId],
    queryFn: () => validateScene(activeSceneId ?? ""),
    enabled: activeSceneId !== null
  });

  const createRoom = useMutation({
    mutationFn: async () => {
      if (!projectQuery.data || activeProjectId === null) {
        throw new Error("No project selected");
      }
      const scene = roomScene(projectQuery.data);
      return createScene(activeProjectId, scene, projectQuery.data.revision);
    },
    onSuccess: async (result) => {
      setSelectedSceneId("scene_demo_room");
      await queryClient.invalidateQueries({ queryKey: ["project", result.document.project.id] });
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
    }
  });

  const selectedScene = useMemo(
    () => scenes.find((scene) => scene.id === activeSceneId) ?? scenes[0],
    [activeSceneId, scenes]
  );

  if (projectsQuery.isLoading || projectQuery.isLoading) {
    return (
      <section className="page-surface" aria-label="Scenes">
        <Spinner label="Loading scenes" />
      </section>
    );
  }

  return (
    <section className="scene-editor-layout" aria-label="Scenes">
      <div className="scene-main">
        <div className="section-heading">
          <div>
            <Title2 as="h2">Scenes</Title2>
            <Text className="muted-text">{scenes.length} in selected project</Text>
          </div>
          <Button
            appearance="primary"
            icon={<Plus size={16} />}
            onClick={() => createRoom.mutate()}
            disabled={!projectQuery.data || createRoom.isPending}
          >
            Create Room
          </Button>
        </div>

        <div className="scene-stage" aria-label="Scene spatial preview">
          {selectedScene ? (
            <>
              {selectedScene.objects.map((object) => (
                <div
                  key={object.id}
                  className={`scene-object scene-object-${object.kind}`}
                  style={{
                    left: `${((object.bounds[0] + 5) / 12) * 100}%`,
                    bottom: `${((object.bounds[1] + 1) / 6) * 100}%`,
                    width: `${((object.bounds[2] - object.bounds[0]) / 12) * 100}%`,
                    height: `${((object.bounds[3] - object.bounds[1]) / 6) * 100}%`
                  }}
                  title={object.name}
                />
              ))}
              {selectedScene.actors.map((actor) => (
                <div
                  key={actor.id}
                  className="scene-actor"
                  style={{
                    left: `${((actor.root_transform.position[0] + 5) / 12) * 100}%`,
                    bottom: `${((actor.root_transform.position[1] + 1) / 6) * 100}%`
                  }}
                  title={actor.display_name}
                >
                  {actor.display_name.slice(0, 1)}
                </div>
              ))}
            </>
          ) : (
            <Text>No scene selected.</Text>
          )}
        </div>
      </div>

      <aside className="scene-side">
        <Title3 as="h3">Project</Title3>
        <div className="scene-list">
          {projectsQuery.data?.map((project) => (
            <button
              type="button"
              className="scene-list-button"
              aria-pressed={project.id === activeProjectId}
              key={project.id}
              onClick={() => {
                setSelectedProjectId(project.id);
                setSelectedSceneId(null);
              }}
            >
              <Text>{project.name}</Text>
            </button>
          ))}
        </div>

        <Title3 as="h3">Objects</Title3>
        <div className="scene-list">
          {selectedScene?.objects.map((object) => (
            <div className="scene-inspector-row" key={object.id}>
              <Text weight="semibold">{object.name}</Text>
              <Text size={200} className="muted-text">
                {object.kind} · {object.colliders.length} colliders · {object.anchors.length} anchors
              </Text>
              <div className="scene-badges">
                {object.walkable ? <Badge color="success">walkable</Badge> : null}
                {object.blocked ? <Badge color="danger">blocked</Badge> : null}
                {object.affordances.map((affordance) => (
                  <Badge key={`${object.id}-${affordance.type}`} appearance="tint">
                    {affordance.type}
                  </Badge>
                ))}
              </div>
            </div>
          ))}
        </div>

        <Title3 as="h3">Snapshot</Title3>
        <Button
          icon={<Eye size={16} />}
          disabled={activeSceneId === null}
          onClick={() => void snapshotQuery.refetch()}
        >
          Refresh
        </Button>
        <Text size={200} className="muted-text">
          {snapshotQuery.data?.byte_length ?? 0} bytes · {validationQuery.data?.issues.length ?? 0} issues
        </Text>
        <pre className="scene-snapshot-preview">{snapshotQuery.data?.canonical_json ?? ""}</pre>
      </aside>
    </section>
  );
}
