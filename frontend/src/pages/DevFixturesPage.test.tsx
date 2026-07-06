import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DevFixturesPage } from "./DevFixturesPage";

describe("DevFixturesPage", () => {
  it("shows validated counts and computed world endpoints", () => {
    render(
      <FluentProvider theme={webLightTheme}>
        <DevFixturesPage />
      </FluentProvider>
    );

    expect(screen.getByText("Bones")).toBeInTheDocument();
    expect(screen.getByText("25")).toBeInTheDocument();
    expect(screen.getByText("0 issues")).toBeInTheDocument();

    // Head bone endpoints from the canonical biped: origin (0, 3), tip (0, 3.45).
    expect(screen.getByRole("table", { name: /computed world endpoints/i })).toBeInTheDocument();
    expect(screen.getByText("head")).toBeInTheDocument();
    expect(screen.getByText("(0.000, 3.450)")).toBeInTheDocument();
  });
});
