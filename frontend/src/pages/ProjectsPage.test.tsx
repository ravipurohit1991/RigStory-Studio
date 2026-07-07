import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectsPage } from "./ProjectsPage";

const seedProjects = [
  { id: "project_alpha", name: "Alpha Project", revision: "rev_1" },
  { id: "project_beta", name: "Beta Project", revision: "rev_2" }
];

const mockMutations: Record<string, unknown> = {};

function mockMutate(name: string, body?: () => unknown) {
  mockMutations[name] = body ?? (() => undefined);
}

function renderWithSeed(node: ReactNode, seed: (client: QueryClient) => void) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
      mutations: { retry: false }
    }
  });
  seed(queryClient);
  return render(
    <FluentProvider theme={webLightTheme}>
      <QueryClientProvider client={queryClient}>{node}</QueryClientProvider>
    </FluentProvider>
  );
}

const originalFetch = globalThis.fetch;

describe("ProjectsPage", () => {
  beforeEach(() => {
    Object.keys(mockMutations).forEach((key) => delete mockMutations[key]);
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/projects/") && init?.method === "POST" && url.endsWith("/duplicate")) {
        const match = url.match(/\/projects\/([^/]+)\/duplicate/);
        const projectId = match?.[1] ?? "project_unknown";
        const source = seedProjects.find((p) => p.id === projectId) ?? seedProjects[0];
        const body = mockMutations.duplicate ? (mockMutations.duplicate as () => Record<string, unknown>)() : {};
        return {
          ok: true,
          status: 201,
          json: async () => ({
            document: {
              project: { id: `${source.id}_copy`, name: `${source.name} Copy` }
            },
            revision: "rev_copy"
          }),
          text: async () => "",
          ...body
        } as Response;
      }
      if (url.includes("/projects/") && init?.method === "DELETE") {
        const body = mockMutations.delete ? (mockMutations.delete as () => Record<string, unknown>)() : {};
        return { ok: true, status: 204, json: async () => undefined, text: async () => "", ...body } as Response;
      }
      if (url.includes("/projects/") && init?.method === "GET" && url.endsWith("/export")) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "Content-Disposition": 'attachment; filename="alpha.rigstory.zip"' }),
          blob: async () => new Blob(["PK"])
        } as Response;
      }
      return originalFetch(input, init);
    }) as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("lists projects with quick-action buttons", async () => {
    renderWithSeed(<ProjectsPage />, (client) => {
      client.setQueryData(["projects"], seedProjects);
    });

    expect(await screen.findByText("Alpha Project")).toBeInTheDocument();
    expect(screen.getByLabelText("Duplicate Alpha Project")).toBeInTheDocument();
    expect(screen.getByLabelText("Export Alpha Project")).toBeInTheDocument();
    expect(screen.getByLabelText("Delete Alpha Project")).toBeInTheDocument();
  });

  it("duplicates a project when the duplicate action is clicked", async () => {
    renderWithSeed(<ProjectsPage />, (client) => {
      client.setQueryData(["projects"], seedProjects);
    });

    const button = await screen.findByLabelText("Duplicate Alpha Project");
    fireEvent.click(button);

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
  });

  it("exports a project when the export action is clicked", async () => {
    const openedUrls: string[] = [];
    vi.spyOn(window, "open").mockImplementation((url?: string | URL | null) => {
      if (typeof url === "string") {
        openedUrls.push(url);
      }
      return null;
    });

    renderWithSeed(<ProjectsPage />, (client) => {
      client.setQueryData(["projects"], seedProjects);
    });

    const button = await screen.findByLabelText("Export Alpha Project");
    fireEvent.click(button);

    await waitFor(() => {
      expect(openedUrls.length).toBeGreaterThan(0);
    });

    expect(openedUrls[0]).toContain("/projects/project_alpha/export");
  });

  it("opens a confirmation dialog before deleting", async () => {
    renderWithSeed(<ProjectsPage />, (client) => {
      client.setQueryData(["projects"], seedProjects);
    });

    const button = await screen.findByLabelText("Delete Alpha Project");
    fireEvent.click(button);

    expect(await screen.findByText("Delete project?")).toBeInTheDocument();
    expect(await screen.findByText(/and its revision history will be removed/)).toBeInTheDocument();
  });

  it("deletes the project after confirmation", async () => {
    let called = false;
    mockMutate("delete", () => {
      called = true;
      return undefined;
    });

    renderWithSeed(<ProjectsPage />, (client) => {
      client.setQueryData(["projects"], seedProjects);
    });

    const deleteButton = await screen.findByLabelText("Delete Alpha Project");
    fireEvent.click(deleteButton);

    const confirmButton = await screen.findByText("Delete");
    fireEvent.click(confirmButton);

    await waitFor(() => expect(called).toBe(true));
  });
});
