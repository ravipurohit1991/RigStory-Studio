import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const healthPayload = {
  status: "healthy",
  application: { status: "healthy", detail: "app" },
  database: { status: "healthy", detail: "db" },
  assets: { status: "healthy", detail: "assets" },
  ollama: {
    status: "unavailable",
    base_url: "http://localhost:11434",
    detail: "connection refused"
  }
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/projects")) {
        return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
      }
      if (url.endsWith("/health")) {
        return Promise.resolve(new Response(JSON.stringify(healthPayload), { status: 200 }));
      }
      if (url.endsWith("/settings")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              app_name: "RigStory Studio",
              app_version: "0.1.0",
              environment: "local",
              api_base_path: "/api/v1",
              asset_store_path: "./data",
              ollama_base_url: "http://localhost:11434"
            }),
            { status: 200 }
          )
        );
      }
      return Promise.resolve(new Response("Not found", { status: 404 }));
    })
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders the Fluent UI project shell", async () => {
    render(<App />);

    expect(screen.getByRole("tab", { name: /projects/i })).toBeInTheDocument();
    expect(await screen.findByText("No projects yet.")).toBeInTheDocument();
  });
});
