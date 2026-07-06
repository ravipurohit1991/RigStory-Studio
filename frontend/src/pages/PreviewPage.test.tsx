import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { PreviewPage } from "./PreviewPage";

// Pre-seed the query cache (with staleTime Infinity so nothing refetches) instead
// of stubbing fetch. This keeps the list -> selection -> detail resolution
// synchronous and deterministic in the test environment.
function renderWithSeed(node: ReactNode, seed: (client: QueryClient) => void) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } }
  });
  seed(queryClient);
  return render(
    <FluentProvider theme={webLightTheme}>
      <QueryClientProvider client={queryClient}>{node}</QueryClientProvider>
    </FluentProvider>
  );
}

describe("PreviewPage", () => {
  it("shows an empty state when there are no projects", async () => {
    renderWithSeed(<PreviewPage />, (client) => {
      client.setQueryData(["projects"], []);
    });

    expect(await screen.findByText("No projects yet.")).toBeInTheDocument();
  });

  describe("with a project that has no compiled clip", () => {
    const seed = (client: QueryClient) => {
      client.setQueryData(["projects"], [{ id: "project_demo", name: "Demo", revision: "rev_1" }]);
      client.setQueryData(["project", "project_demo"], {
        document: { scenes: [], clips: [] },
        revision: "rev_1"
      });
    };

    it("prompts the user to compile motion first", async () => {
      renderWithSeed(<PreviewPage />, seed);

      expect(await screen.findByText("This project has no animation yet.")).toBeInTheDocument();
    });

    it("offers a shortcut to the Motion step", async () => {
      const onGoToMotion = vi.fn();
      renderWithSeed(<PreviewPage onGoToMotion={onGoToMotion} />, seed);

      const button = await screen.findByRole("button", { name: /go to motion/i });
      fireEvent.click(button);

      expect(onGoToMotion).toHaveBeenCalledTimes(1);
    });
  });
});
