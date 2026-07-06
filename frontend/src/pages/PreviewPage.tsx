import {
  Badge,
  Button,
  Field,
  Select,
  Slider,
  Spinner,
  Switch,
  Text,
  Title2
} from "@fluentui/react-components";
import { useQuery } from "@tanstack/react-query";
import { Clapperboard, Pause, Play, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { getProject, getProjects } from "../api/client";
import { createPlayer, type RigStoryPlayer } from "../runtime";

const CANVAS_WIDTH = 960;
const CANVAS_HEIGHT = 540;

interface PreviewPageProps {
  /** Jump to the Motion step (used when a project has no compiled clip yet). */
  readonly onGoToMotion?: () => void;
}

function formatTime(seconds: number): string {
  return `${seconds.toFixed(2)}s`;
}

export function PreviewPage({ onGoToMotion }: PreviewPageProps) {
  const projectsQuery = useQuery({ queryKey: ["projects"], queryFn: getProjects });
  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data]);

  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  useEffect(() => {
    if (selectedProjectId === null && projects.length > 0) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, selectedProjectId]);

  const projectQuery = useQuery({
    queryKey: ["project", selectedProjectId],
    queryFn: () => getProject(selectedProjectId ?? ""),
    enabled: selectedProjectId !== null
  });
  const projectDocument = projectQuery.data?.document ?? null;
  const clips = useMemo(() => projectDocument?.clips ?? [], [projectDocument]);

  const [selectedClipId, setSelectedClipId] = useState<string | null>(null);
  useEffect(() => {
    // Snap to the first clip whenever the loaded project (and its clips) change.
    setSelectedClipId(clips.length > 0 ? clips[0].id : null);
  }, [clips]);

  const selectedClip = useMemo(
    () => clips.find((clip) => clip.id === selectedClipId) ?? null,
    [clips, selectedClipId]
  );
  const scene = useMemo(
    () => projectDocument?.scenes.find((candidate) => candidate.id === selectedClip?.scene_id) ?? null,
    [projectDocument, selectedClip]
  );

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const playerRef = useRef<RigStoryPlayer | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [loop, setLoop] = useState(true);
  const [playerError, setPlayerError] = useState<string | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (
      canvas === null ||
      projectDocument === null ||
      selectedClipId === null ||
      !clips.some((clip) => clip.id === selectedClipId)
    ) {
      return;
    }

    let player: RigStoryPlayer;
    try {
      player = createPlayer({
        document: projectDocument,
        clipId: selectedClipId,
        canvas,
        width: CANVAS_WIDTH,
        height: CANVAS_HEIGHT,
        background: "#f8fafc",
        loop
      });
    } catch (error) {
      setPlayerError(error instanceof Error ? error.message : "Unable to start playback.");
      return;
    }

    playerRef.current = player;
    setPlayerError(null);
    setDuration(player.duration);
    setTime(player.time);
    setPlaying(false);
    const offFrame = player.on("frame", (value) => setTime(value));
    const offFinish = player.on("finish", () => setPlaying(false));
    player.renderFrame();

    return () => {
      offFrame();
      offFinish();
      player.dispose();
      playerRef.current = null;
    };
    // `loop` is applied live via setLoop (below) so toggling it never restarts playback.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectDocument, selectedClipId, clips]);

  useEffect(() => {
    playerRef.current?.setLoop(loop);
  }, [loop]);

  const togglePlay = () => {
    const player = playerRef.current;
    if (player === null) {
      return;
    }
    if (player.playing) {
      player.pause();
      setPlaying(false);
    } else {
      player.play();
      setPlaying(true);
    }
  };

  const restart = () => {
    playerRef.current?.seek(0);
    setTime(0);
  };

  const onScrub = (value: number) => {
    playerRef.current?.seek(value);
    setTime(value);
  };

  if (projectsQuery.isLoading) {
    return (
      <section className="page-surface" aria-label="Player">
        <Spinner label="Loading player" />
      </section>
    );
  }

  if (projects.length === 0) {
    return (
      <section className="page-surface" aria-label="Player">
        <Title2 as="h2">Player</Title2>
        <div className="empty-state">
          <Text weight="semibold">No projects yet.</Text>
          <Text size={200} className="muted-text">
            Create a project, build a scene, then compile motion — the finished animation plays here.
          </Text>
        </div>
      </section>
    );
  }

  return (
    <section className="player-layout" aria-label="Player">
      <div className="section-heading">
        <div>
          <Title2 as="h2">Player</Title2>
          <Text className="muted-text">
            Watch the compiled scene play back — your characters moving and interacting.
          </Text>
        </div>
        <div className="rig-heading-badges">
          {scene
            ? scene.actors.map((actor) => (
                <Badge key={actor.id} appearance="tint" color="brand">
                  {actor.display_name}
                </Badge>
              ))
            : null}
        </div>
      </div>

      <div className="player-toolbar">
        <Field label="Project">
          <Select
            value={selectedProjectId ?? ""}
            onChange={(event) => setSelectedProjectId(event.target.value)}
          >
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Animation clip">
          <Select
            aria-label="Animation clip"
            value={selectedClipId ?? ""}
            disabled={clips.length === 0}
            onChange={(event) => setSelectedClipId(event.target.value)}
          >
            {clips.length === 0 ? <option value="">No clips compiled</option> : null}
            {clips.map((clip) => (
              <option key={clip.id} value={clip.id}>
                {clip.name}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {projectQuery.isLoading ? (
        <Spinner label="Loading project" />
      ) : clips.length === 0 ? (
        <div className="empty-state">
          <Text weight="semibold">This project has no animation yet.</Text>
          <Text size={200} className="muted-text">
            Go to the Motion step, describe an action, and compile it — then return here to watch it play.
          </Text>
          {onGoToMotion ? (
            <Button appearance="primary" icon={<Clapperboard size={16} />} onClick={onGoToMotion}>
              Go to Motion
            </Button>
          ) : null}
        </div>
      ) : (
        <>
          <div className="player-stage-host">
            <canvas
              ref={canvasRef}
              className="player-canvas"
              width={CANVAS_WIDTH}
              height={CANVAS_HEIGHT}
              aria-label="Scene playback"
            />
          </div>

          {playerError ? (
            <Text role="alert" className="warning-text">
              Playback unavailable: {playerError}
            </Text>
          ) : null}

          <div className="player-transport">
            <Button
              appearance="primary"
              icon={playing ? <Pause size={16} /> : <Play size={16} />}
              onClick={togglePlay}
            >
              {playing ? "Pause" : "Play"}
            </Button>
            <Button icon={<RotateCcw size={16} />} onClick={restart}>
              Restart
            </Button>
            <Slider
              className="player-scrub"
              aria-label="Scrub timeline"
              min={0}
              max={duration > 0 ? duration : 1}
              step={0.01}
              value={time}
              onChange={(_event, data) => onScrub(data.value)}
            />
            <Text className="player-time">
              {formatTime(time)} / {formatTime(duration)}
            </Text>
            <Switch
              checked={loop}
              label="Loop"
              onChange={(_event, data) => setLoop(data.checked)}
            />
          </div>

          <dl className="numeric-inspector player-clip-meta">
            <div>
              <dt>Clip</dt>
              <dd>{selectedClip?.name}</dd>
            </div>
            <div>
              <dt>Scene</dt>
              <dd>{scene?.name ?? selectedClip?.scene_id}</dd>
            </div>
            <div>
              <dt>Duration</dt>
              <dd>{formatTime(duration)}</dd>
            </div>
            <div>
              <dt>Tracks</dt>
              <dd>{selectedClip?.tracks.length ?? 0}</dd>
            </div>
          </dl>
        </>
      )}
    </section>
  );
}
