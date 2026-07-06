import { describe, expect, it } from "vitest";

import {
  createEmptyHistory,
  createReplaceStateCommand,
  redo,
  runCommand,
  undo
} from "./commands";

interface CounterState {
  readonly value: number;
}

function replaceValue(value: number, mergeKey?: string) {
  return createReplaceStateCommand<CounterState>({
    id: "counter.set",
    label: "Set counter",
    state: { value },
    mergeKey
  });
}

describe("editor command history", () => {
  it("undoes and redoes snapshot commands", () => {
    const initial = { value: 0 };
    const first = runCommand(initial, createEmptyHistory<CounterState>(), replaceValue(1));
    const second = runCommand(first.state, first.history, replaceValue(2));

    const undone = undo(second.state, second.history);
    expect(undone.state).toEqual({ value: 1 });

    const redone = redo(undone.state, undone.history);
    expect(redone.state).toEqual({ value: 2 });
  });

  it("merges continuous commands into one undo entry", () => {
    const initial = { value: 0 };
    const first = runCommand(initial, createEmptyHistory<CounterState>(), replaceValue(1, "drag"), {
      mergeWithPrevious: true
    });
    const second = runCommand(first.state, first.history, replaceValue(2, "drag"), {
      mergeWithPrevious: true
    });
    const third = runCommand(second.state, second.history, replaceValue(3, "drag"), {
      mergeWithPrevious: true
    });

    expect(third.history.undoStack).toHaveLength(1);
    expect(undo(third.state, third.history).state).toEqual(initial);
  });
});
