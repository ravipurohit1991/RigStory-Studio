import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RigEditorPage } from "./RigEditorPage";
import type { RigStageBoneDragEvent } from "../engine/renderer/RigStageAdapter";

const rigStageMocks = vi.hoisted(() => {
  let lastOptions:
    | {
        onSelectBone?: (boneId: string | null) => void;
        onDragBone?: (event: RigStageBoneDragEvent) => void;
      }
    | null = null;
  const adapter = {
    destroy: vi.fn(),
    mount: vi.fn(() => Promise.resolve()),
    resize: vi.fn(),
    setCamera: vi.fn(),
    updateRig: vi.fn()
  };
  const createRigStageAdapter = vi.fn(
    (options: {
      onSelectBone?: (boneId: string | null) => void;
      onDragBone?: (event: RigStageBoneDragEvent) => void;
    }) => {
      lastOptions = options;
      return adapter;
    }
  );
  return {
    adapter,
    createRigStageAdapter,
    getLastOptions: () => lastOptions
  };
});

vi.mock("../engine/renderer/RigStageAdapter", () => ({
  createRigStageAdapter: rigStageMocks.createRigStageAdapter
}));

describe("RigEditorPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("mounts the renderer adapter with the canonical rig", async () => {
    render(<RigEditorPage />);

    expect(screen.getByRole("img", { name: /rig stage viewport/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /hips/i })).toHaveAttribute("aria-pressed", "true");

    await waitFor(() => expect(rigStageMocks.adapter.updateRig).toHaveBeenCalled());
    expect(rigStageMocks.adapter.updateRig).toHaveBeenLastCalledWith(
      expect.objectContaining({
        rig: expect.objectContaining({ id: "rig_biped_alpha" }),
        selectedBoneId: "hips",
        showDebugAxes: true,
        showLabels: true
      })
    );
  });

  it("mirrors bone tree and stage selections into the inspector", async () => {
    render(<RigEditorPage />);
    await waitFor(() => expect(rigStageMocks.adapter.updateRig).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: /forearm_r/i }));

    expect(screen.getByRole("button", { name: /forearm_r/i })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    await waitFor(() =>
      expect(rigStageMocks.adapter.updateRig).toHaveBeenLastCalledWith(
        expect.objectContaining({ selectedBoneId: "forearm_r" })
      )
    );

    act(() => {
      rigStageMocks.getLastOptions()?.onSelectBone?.("head");
    });
    await waitFor(() =>
      expect(rigStageMocks.adapter.updateRig).toHaveBeenLastCalledWith(
        expect.objectContaining({ selectedBoneId: "head" })
      )
    );
    expect(screen.getByRole("button", { name: /^head/i })).toHaveAttribute("aria-pressed", "true");
  });

  it("passes overlay toggles and view reset to the adapter", async () => {
    render(<RigEditorPage />);
    await waitFor(() => expect(rigStageMocks.adapter.updateRig).toHaveBeenCalled());

    fireEvent.click(screen.getByLabelText("Labels"));
    await waitFor(() =>
      expect(rigStageMocks.adapter.updateRig).toHaveBeenLastCalledWith(
        expect.objectContaining({ showLabels: false })
      )
    );

    fireEvent.click(screen.getByRole("button", { name: /reset view/i }));
    expect(rigStageMocks.adapter.setCamera).toHaveBeenCalledWith(
      expect.objectContaining({ center: { x: 0, y: 1.6 }, zoom: 1 })
    );
  });

  it("edits selected setup values from the numeric inspector and supports undo redo", async () => {
    render(<RigEditorPage />);
    await waitFor(() => expect(rigStageMocks.adapter.updateRig).toHaveBeenCalled());

    const localX = screen.getByLabelText("Local X");
    fireEvent.change(localX, { target: { value: "0.25" } });
    fireEvent.blur(localX);

    await waitFor(() =>
      expect(rigStageMocks.adapter.updateRig).toHaveBeenLastCalledWith(
        expect.objectContaining({
          rig: expect.objectContaining({
            bones: expect.arrayContaining([
              expect.objectContaining({
                id: "hips",
                setup_transform: expect.objectContaining({ position: [0.25, 1.7] })
              })
            ])
          })
        })
      )
    );
    expect(screen.getByText("Unsaved")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() =>
      expect(rigStageMocks.adapter.updateRig).toHaveBeenLastCalledWith(
        expect.objectContaining({
          rig: expect.objectContaining({
            bones: expect.arrayContaining([
              expect.objectContaining({
                id: "hips",
                setup_transform: expect.objectContaining({ position: [0, 1.7] })
              })
            ])
          })
        })
      )
    );

    fireEvent.click(screen.getByRole("button", { name: "Redo" }));
    await waitFor(() =>
      expect(rigStageMocks.adapter.updateRig).toHaveBeenLastCalledWith(
        expect.objectContaining({
          rig: expect.objectContaining({
            bones: expect.arrayContaining([
              expect.objectContaining({
                id: "hips",
                setup_transform: expect.objectContaining({ position: [0.25, 1.7] })
              })
            ])
          })
        })
      )
    );
  });

  it("locks setup position and length controls in animation mode", async () => {
    render(<RigEditorPage />);
    await waitFor(() => expect(rigStageMocks.adapter.updateRig).toHaveBeenCalled());

    fireEvent.click(screen.getByLabelText("Animate"));

    expect(screen.getByLabelText("Local X")).toBeDisabled();
    expect(screen.getByLabelText("Local Y")).toBeDisabled();
    expect(screen.getByLabelText("Length")).toBeDisabled();
    expect(screen.getByLabelText("Rotation")).not.toBeDisabled();
  });

  it("supports timeline zoom, scrollable tracks, and loop range editing", async () => {
    render(<RigEditorPage />);
    await waitFor(() => expect(rigStageMocks.adapter.updateRig).toHaveBeenCalled());

    expect(screen.getByRole("region", { name: /timeline tracks/i })).toBeInTheDocument();

    const zoom = screen.getByLabelText("Timeline zoom");
    fireEvent.change(zoom, { target: { value: "2" } });
    expect(zoom).toHaveValue("2");

    fireEvent.click(screen.getByLabelText("Loop"));
    const loopStart = screen.getByLabelText("Loop start");
    const loopEnd = screen.getByLabelText("Loop end");

    fireEvent.change(loopStart, { target: { value: "0.2" } });
    fireEvent.blur(loopStart);
    fireEvent.change(loopEnd, { target: { value: "0.8" } });
    fireEvent.blur(loopEnd);

    expect(screen.getByText("Unsaved")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /seek to loop start/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /seek to loop end/i })).toBeEnabled();
  });

  it("passes nearby onion-skin poses to the renderer in animation mode", async () => {
    render(<RigEditorPage />);
    await waitFor(() => expect(rigStageMocks.adapter.updateRig).toHaveBeenCalled());

    fireEvent.click(screen.getByLabelText("Animate"));

    await waitFor(() =>
      expect(rigStageMocks.adapter.updateRig).toHaveBeenLastCalledWith(
        expect.objectContaining({
          onionSkins: expect.arrayContaining([
            expect.objectContaining({ alpha: expect.any(Number), rig: expect.any(Object) })
          ])
        })
      )
    );
  });

  it("pumps playback frames directly to the renderer adapter", async () => {
    const callbacks: FrameRequestCallback[] = [];
    const rafSpy = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((callback: FrameRequestCallback) => {
        callbacks.push(callback);
        return callbacks.length;
      });
    const cancelSpy = vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
    const { unmount } = render(<RigEditorPage />);
    await waitFor(() => expect(rigStageMocks.adapter.updateRig).toHaveBeenCalled());
    const callsBeforePlayback = rigStageMocks.adapter.updateRig.mock.calls.length;

    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    await waitFor(() => expect(callbacks.length).toBeGreaterThan(0));

    act(() => {
      callbacks.shift()?.(performance.now() + 160);
    });

    expect(rigStageMocks.adapter.updateRig.mock.calls.length).toBeGreaterThan(callsBeforePlayback);

    unmount();
    rafSpy.mockRestore();
    cancelSpy.mockRestore();
  });

  it("applies continuous stage body drags as one undoable setup edit", async () => {
    render(<RigEditorPage />);
    await waitFor(() => expect(rigStageMocks.adapter.updateRig).toHaveBeenCalled());

    const dragBase = {
      hit: { boneId: "root", kind: "body" as const, distancePx: 0 },
      screenPoint: { x: 100, y: 100 },
      shiftKey: false
    };

    act(() => {
      rigStageMocks.getLastOptions()?.onDragBone?.({
        ...dragBase,
        phase: "start",
        worldPoint: { x: 0, y: 0 }
      });
      rigStageMocks.getLastOptions()?.onDragBone?.({
        ...dragBase,
        phase: "update",
        worldPoint: { x: 0.2, y: 0.3 }
      });
      rigStageMocks.getLastOptions()?.onDragBone?.({
        ...dragBase,
        phase: "update",
        worldPoint: { x: 0.4, y: 0.6 }
      });
    });

    await waitFor(() =>
      expect(rigStageMocks.adapter.updateRig).toHaveBeenLastCalledWith(
        expect.objectContaining({
          rig: expect.objectContaining({
            bones: expect.arrayContaining([
              expect.objectContaining({
                id: "root",
                setup_transform: expect.objectContaining({ position: [0.4, 0.6] })
              })
            ])
          })
        })
      )
    );

    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() =>
      expect(rigStageMocks.adapter.updateRig).toHaveBeenLastCalledWith(
        expect.objectContaining({
          rig: expect.objectContaining({
            bones: expect.arrayContaining([
              expect.objectContaining({
                id: "root",
                setup_transform: expect.objectContaining({ position: [0, 0] })
              })
            ])
          })
        })
      )
    );
  });
});
