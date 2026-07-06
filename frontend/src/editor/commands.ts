export interface EditorCommand<TState> {
  readonly id: string;
  readonly label: string;
  apply(state: TState): TState;
  invert(before: TState): EditorCommand<TState>;
  mergeWith?(next: EditorCommand<TState>): EditorCommand<TState> | null;
}

export interface EditorHistory<TState> {
  readonly undoStack: readonly EditorCommand<TState>[];
  readonly redoStack: readonly EditorCommand<TState>[];
}

export interface CommandResult<TState> {
  readonly state: TState;
  readonly history: EditorHistory<TState>;
}

export interface RunCommandOptions {
  readonly mergeWithPrevious?: boolean;
}

interface ReplaceStateCommand<TState> extends EditorCommand<TState> {
  readonly kind: "replace-state";
  readonly target: TState;
  readonly mergeKey: string | null;
}

export function createEmptyHistory<TState>(): EditorHistory<TState> {
  return {
    undoStack: [],
    redoStack: []
  };
}

function isReplaceStateCommand<TState>(
  command: EditorCommand<TState>
): command is ReplaceStateCommand<TState> {
  return "kind" in command && command.kind === "replace-state";
}

export function createReplaceStateCommand<TState>(options: {
  readonly id: string;
  readonly label: string;
  readonly state: TState;
  readonly mergeKey?: string | null;
}): EditorCommand<TState> {
  const mergeKey = options.mergeKey ?? null;
  const command: ReplaceStateCommand<TState> = {
    kind: "replace-state",
    id: options.id,
    label: options.label,
    target: options.state,
    mergeKey,
    apply: () => options.state,
    invert: (before) =>
      createReplaceStateCommand({
        id: options.id,
        label: options.label,
        state: before,
        mergeKey
      }),
    mergeWith: (next) => {
      if (!isReplaceStateCommand(next) || mergeKey === null || next.mergeKey !== mergeKey) {
        return null;
      }
      return command;
    }
  };
  return command;
}

export function runCommand<TState>(
  state: TState,
  history: EditorHistory<TState>,
  command: EditorCommand<TState>,
  options: RunCommandOptions = {}
): CommandResult<TState> {
  const nextState = command.apply(state);
  if (Object.is(nextState, state)) {
    return { state, history };
  }

  const undoCommand = command.invert(state);
  const undoStack = [...history.undoStack];
  if (options.mergeWithPrevious && undoStack.length > 0) {
    const previous = undoStack[undoStack.length - 1];
    const merged = previous.mergeWith?.(undoCommand) ?? null;
    if (merged === null) {
      undoStack.push(undoCommand);
    } else {
      undoStack[undoStack.length - 1] = merged;
    }
  } else {
    undoStack.push(undoCommand);
  }

  return {
    state: nextState,
    history: {
      undoStack,
      redoStack: []
    }
  };
}

export function undo<TState>(
  state: TState,
  history: EditorHistory<TState>
): CommandResult<TState> {
  const command = history.undoStack.at(-1);
  if (command === undefined) {
    return { state, history };
  }
  const nextState = command.apply(state);
  return {
    state: nextState,
    history: {
      undoStack: history.undoStack.slice(0, -1),
      redoStack: [...history.redoStack, command.invert(state)]
    }
  };
}

export function redo<TState>(
  state: TState,
  history: EditorHistory<TState>
): CommandResult<TState> {
  const command = history.redoStack.at(-1);
  if (command === undefined) {
    return { state, history };
  }
  const nextState = command.apply(state);
  return {
    state: nextState,
    history: {
      undoStack: [...history.undoStack, command.invert(state)],
      redoStack: history.redoStack.slice(0, -1)
    }
  };
}
