import {
  Body1,
  Button,
  Caption1,
  Tab,
  TabList,
  Text,
  Title3,
  Tooltip
} from "@fluentui/react-components";
import type { SelectTabData, SelectTabEvent } from "@fluentui/react-components";
import {
  ArrowLeft,
  ArrowRight,
  Bone,
  Check,
  Clapperboard,
  FlaskConical,
  Folder,
  HeartPulse,
  Map,
  MonitorPlay,
  RefreshCw,
  Settings,
  UserRound
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useState } from "react";

import { CharacterBuilderPage } from "../pages/CharacterBuilderPage";
import { DevFixturesPage } from "../pages/DevFixturesPage";
import { HealthPage } from "../pages/HealthPage";
import { MotionPage } from "../pages/MotionPage";
import { PreviewPage } from "../pages/PreviewPage";
import { ProjectsPage } from "../pages/ProjectsPage";
import { RigEditorPage } from "../pages/RigEditorPage";
import { SceneEditorPage } from "../pages/SceneEditorPage";
import { SettingsPage } from "../pages/SettingsPage";

type ViewKey =
  | "projects"
  | "characters"
  | "rig"
  | "scenes"
  | "motion"
  | "preview"
  | "health"
  | "settings"
  | "dev";

interface ViewMeta {
  key: ViewKey;
  /** Accessible tab label — kept stable for tests and screen readers. */
  label: string;
  icon: LucideIcon;
  description: string;
}

const SHOW_DEV_TOOLS = import.meta.env.DEV;

// The five ordered steps of the creative workflow. Order matters: it drives the
// numbered stepper, the "Step N of M" indicator, and the Back / Continue buttons.
const WORKFLOW_STEPS: readonly ViewMeta[] = [
  {
    key: "projects",
    label: "Projects",
    icon: Folder,
    description: "Open an existing workspace or create a new project to begin animating."
  },
  {
    key: "characters",
    label: "Characters",
    icon: UserRound,
    description: "Design or generate a character, then tune its proportions, palette, and style."
  },
  {
    key: "rig",
    label: "Rig Editor",
    icon: Bone,
    description: "Place bones and attachments so your character is ready to pose and animate."
  },
  {
    key: "scenes",
    label: "Scenes",
    icon: Map,
    description: "Arrange your character and props, then set the ground plane and world bounds."
  },
  {
    key: "motion",
    label: "Motion",
    icon: Clapperboard,
    description: "Describe the action, review the generated plan, and compile deterministic motion."
  },
  {
    key: "preview",
    label: "Player",
    icon: MonitorPlay,
    description: "Play back the compiled scene and watch your characters move and interact."
  }
];

// Supporting pages that sit outside the linear workflow.
const TOOL_VIEWS: readonly ViewMeta[] = [
  {
    key: "health",
    label: "Health",
    icon: HeartPulse,
    description: "Live status of the application services and the local Ollama runtime."
  },
  {
    key: "settings",
    label: "Settings",
    icon: Settings,
    description: "Workspace configuration and local model connectivity."
  }
];

const DEV_VIEW: ViewMeta = {
  key: "dev",
  label: "Dev Fixtures",
  icon: FlaskConical,
  description: "Developer fixtures and sample data for exercising the app."
};

const TOOL_VIEWS_ALL: readonly ViewMeta[] = SHOW_DEV_TOOLS
  ? [...TOOL_VIEWS, DEV_VIEW]
  : TOOL_VIEWS;

const ALL_VIEWS: readonly ViewMeta[] = [...WORKFLOW_STEPS, ...TOOL_VIEWS_ALL];

function isViewKey(value: unknown): value is ViewKey {
  return ALL_VIEWS.some((view) => view.key === value);
}

type StepState = "done" | "current" | "upcoming";

function StepChip({ index, state }: { index: number; state: StepState }) {
  return (
    <span className={`nav-step nav-step--${state}`} aria-hidden="true">
      {state === "done" ? <Check size={13} strokeWidth={3} /> : index + 1}
    </span>
  );
}

export function AppShell() {
  const [activeView, setActiveView] = useState<ViewKey>("projects");

  const onTabSelect = (_event: SelectTabEvent, data: SelectTabData) => {
    if (isViewKey(data.value)) {
      setActiveView(data.value);
    }
  };

  const stepIndex = WORKFLOW_STEPS.findIndex((step) => step.key === activeView);
  const isWorkflow = stepIndex >= 0;
  const activeMeta = ALL_VIEWS.find((view) => view.key === activeView) ?? WORKFLOW_STEPS[0];
  const prevStep = isWorkflow && stepIndex > 0 ? WORKFLOW_STEPS[stepIndex - 1] : null;
  const nextStep =
    isWorkflow && stepIndex < WORKFLOW_STEPS.length - 1 ? WORKFLOW_STEPS[stepIndex + 1] : null;

  return (
    <div className="app-shell">
      <aside className="rail" aria-label="Primary">
        <div className="brand-lockup">
          <div className="brand-mark">RS</div>
          <div className="brand-text">
            <Text weight="semibold">RigStory</Text>
            <Text size={200} className="muted-text">
              Studio
            </Text>
          </div>
        </div>

        <nav className="nav-scroll" aria-label="Sections">
          <div className="nav-section">
            <Text as="h2" className="nav-section-label">
              Workflow
            </Text>
            <TabList
              selectedValue={activeView}
              onTabSelect={onTabSelect}
              vertical
              size="large"
              className="nav-tabs"
            >
              {WORKFLOW_STEPS.map((step, index) => {
                const state: StepState =
                  index < stepIndex ? "done" : index === stepIndex ? "current" : "upcoming";
                return (
                  <Tab key={step.key} value={step.key} icon={<StepChip index={index} state={state} />}>
                    <span className="nav-label">{step.label}</span>
                  </Tab>
                );
              })}
            </TabList>
          </div>

          <div className="nav-section">
            <Text as="h2" className="nav-section-label">
              Tools
            </Text>
            <TabList
              selectedValue={activeView}
              onTabSelect={onTabSelect}
              vertical
              size="large"
              className="nav-tabs"
            >
              {TOOL_VIEWS_ALL.map((tool) => {
                const Icon = tool.icon;
                return (
                  <Tab key={tool.key} value={tool.key} icon={<Icon size={18} />}>
                    <span className="nav-label">{tool.label}</span>
                  </Tab>
                );
              })}
            </TabList>
          </div>
        </nav>

        <div className="rail-footer">
          <span className="status-dot" aria-hidden="true" />
          <Caption1 className="muted-text">Local-first · saved on this machine</Caption1>
        </div>
      </aside>

      <header className="topbar">
        <div className="topbar-lead">
          <div className="breadcrumb">
            <span>{isWorkflow ? "Workflow" : "Tools"}</span>
            <span className="breadcrumb-sep" aria-hidden="true">
              /
            </span>
            <span className="breadcrumb-current">{activeMeta.label}</span>
            {isWorkflow ? (
              <span className="step-pill">
                Step {stepIndex + 1} of {WORKFLOW_STEPS.length}
              </span>
            ) : null}
          </div>
          <Title3 as="h1" className="topbar-title">
            {activeMeta.label}
          </Title3>
          <Body1 className="topbar-desc">{activeMeta.description}</Body1>
        </div>

        <div className="topbar-actions">
          {prevStep ? (
            <Button
              appearance="secondary"
              icon={<ArrowLeft size={16} />}
              onClick={() => setActiveView(prevStep.key)}
            >
              Back
            </Button>
          ) : null}
          {nextStep ? (
            <Button
              appearance="primary"
              iconPosition="after"
              icon={<ArrowRight size={16} />}
              aria-label={`Continue to ${nextStep.label}`}
              onClick={() => setActiveView(nextStep.key)}
            >
              Continue
            </Button>
          ) : null}
          <Tooltip content="Refresh current view" relationship="label">
            <Button
              appearance="subtle"
              aria-label="Refresh current view"
              icon={<RefreshCw size={18} />}
              onClick={() => window.location.reload()}
            />
          </Tooltip>
        </div>
      </header>

      <main className="workspace" tabIndex={-1}>
        {activeView === "projects" ? <ProjectsPage /> : null}
        {activeView === "characters" ? <CharacterBuilderPage /> : null}
        {activeView === "rig" ? <RigEditorPage /> : null}
        {activeView === "scenes" ? <SceneEditorPage /> : null}
        {activeView === "motion" ? <MotionPage /> : null}
        {activeView === "preview" ? (
          <PreviewPage onGoToMotion={() => setActiveView("motion")} />
        ) : null}
        {activeView === "health" ? <HealthPage /> : null}
        {activeView === "settings" ? <SettingsPage /> : null}
        {activeView === "dev" && SHOW_DEV_TOOLS ? <DevFixturesPage /> : null}
      </main>

      <footer className="statusbar">
        <span className="status-dot" aria-hidden="true" />
        <Text size={200} className="muted-text">
          Ready — motion plans compile deterministically.
        </Text>
        <span className="status-spacer" />
        <Text size={200} className="muted-text">
          {isWorkflow ? `Step ${stepIndex + 1} of ${WORKFLOW_STEPS.length}` : "Tools"}
        </Text>
      </footer>
    </div>
  );
}
