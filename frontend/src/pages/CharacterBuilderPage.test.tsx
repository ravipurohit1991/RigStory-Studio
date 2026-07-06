import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_CHARACTER_REQUEST } from "../engine/characterBuilder";
import { CharacterBuilderPage } from "./CharacterBuilderPage";

const rigStageMocks = vi.hoisted(() => {
  const adapter = {
    destroy: vi.fn(),
    mount: vi.fn(() => Promise.resolve()),
    resize: vi.fn(),
    setCamera: vi.fn(),
    updateRig: vi.fn()
  };
  return {
    adapter,
    createRigStageAdapter: vi.fn(() => adapter)
  };
});

vi.mock("../engine/renderer/RigStageAdapter", () => ({
  createRigStageAdapter: rigStageMocks.createRigStageAdapter
}));

class ResizeObserverMock {
  observe = vi.fn();
  disconnect = vi.fn();
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("CharacterBuilderPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("ResizeObserver", ResizeObserverMock);
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          jsonResponse(
            {
              document: {
                project: { name: "Saved Character", id: "project_builder_test" }
              },
              revision: "rev_test"
            },
            201
          )
        )
      )
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders a deterministic generated character in the rig preview", async () => {
    renderWithClient(<CharacterBuilderPage />);

    expect(screen.getByRole("img", { name: /generated character preview/i })).toBeInTheDocument();
    await waitFor(() => expect(rigStageMocks.adapter.updateRig).toHaveBeenCalled());

    expect(rigStageMocks.adapter.updateRig).toHaveBeenLastCalledWith(
      expect.objectContaining({
        rig: expect.objectContaining({
          bones: expect.arrayContaining([expect.objectContaining({ id: "hips" })])
        }),
        attachments: expect.arrayContaining([expect.objectContaining({ id: "part_head" })])
      })
    );
  });

  it("applies presets and regenerates a selected visual region", async () => {
    renderWithClient(<CharacterBuilderPage />);
    await waitFor(() => expect(rigStageMocks.adapter.updateRig).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText("Preset"), { target: { value: "1" } });
    expect(screen.getByLabelText("Name")).toHaveValue("Jon Cutout");

    fireEvent.change(screen.getByLabelText("Region"), { target: { value: "face" } });
    fireEvent.click(screen.getByRole("button", { name: /regenerate/i }));

    await waitFor(() =>
      expect(rigStageMocks.adapter.updateRig).toHaveBeenLastCalledWith(
        expect.objectContaining({
          attachments: expect.arrayContaining([expect.objectContaining({ id: "part_mouth" })])
        })
      )
    );
  });

  it("saves the generated character as a project document", async () => {
    const fetchMock = vi.mocked(fetch);
    renderWithClient(<CharacterBuilderPage />);

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const saveCall = fetchMock.mock.calls.find(
      ([, init]) => init?.method === "POST" && String(init?.body).includes('"characters"')
    );
    expect(saveCall).toBeDefined();
    expect(await screen.findByText(/saved/i)).toBeInTheDocument();
  });

  it("generates a character with Ollama and shows blueprint provenance", async () => {
    const generation = {
      character_id: "char_ai_demo",
      record_id: "gen_ai_demo",
      revision: "rev_after",
      status: "succeeded",
      model_name: "mock-model",
      blueprint: {
        schema_version: "1.0",
        character_name: "Aria",
        presentation: "feminine",
        age_category: "adult",
        style: { family: "flat_vector", outline_weight: 2, detail_level: "medium", symmetry: 0.9 },
        warnings: []
      },
      request: DEFAULT_CHARACTER_REQUEST,
      provenance: [{ field: "name", source: "model", model_value: "Aria" }],
      builder_diagnostics: [],
      warnings: ["Used default footwear"]
    };
    const job = {
      id: "job_ai_1",
      kind: "character_generation",
      state: "succeeded",
      created_at: "2026-07-04T00:00:00Z",
      updated_at: "2026-07-04T00:00:01Z",
      progress: [],
      result: generation,
      retryable: false
    };

    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/ollama/models")) {
          return Promise.resolve(
            jsonResponse({ available: true, base_url: "http://x", models: [{ name: "mock-model" }] })
          );
        }
        if (url.endsWith("/generate")) {
          return Promise.resolve(jsonResponse(job, 202));
        }
        if (url.includes("/jobs/")) {
          return Promise.resolve(jsonResponse(job));
        }
        return Promise.resolve(
          jsonResponse({ document: { project: { id: "project_ai_x", name: "x" } }, revision: "r1" }, 201)
        );
      })
    );

    renderWithClient(<CharacterBuilderPage />);

    const generateButton = await screen.findByRole("button", { name: /generate with ai/i });
    await waitFor(() => expect(generateButton).toBeEnabled());
    fireEvent.click(generateButton);

    expect(await screen.findByText(/Blueprint · Aria/i)).toBeInTheDocument();
    expect(screen.getByText(/Used default footwear/i)).toBeInTheDocument();
    expect(screen.getByText(/name: Aria/i)).toBeInTheDocument();
  });
});
