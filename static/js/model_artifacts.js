export function modelSnapshotForCheckpointEntry(traceEntries = [], entry, currentModel = null) {
  if (!entry) return null;
  const payload = entry.payload || {};
  const direct = entry.working_model_snapshot || payload.model_snapshot || payload.working_model;
  if (direct) return direct;
  const entryIndex = traceEntries.findIndex((candidate) => candidate.id === entry.id);
  for (let index = entryIndex; index >= 0; index -= 1) {
    const candidate = traceEntries[index];
    const candidatePayload = candidate?.payload || {};
    const snapshot =
      candidate?.working_model_snapshot ||
      candidatePayload.model_snapshot ||
      candidatePayload.working_model;
    if (snapshot) return snapshot;
  }
  return currentModel || null;
}

export function traceArtifactStateForEntry(traceEntries = [], entry, options = {}) {
  if (!entry) return options.currentState ? { ...options.currentState } : {
    working_model_snapshot: null,
    structured_model_snapshot: null,
    plantuml_snapshot: "",
    plantuml_url: "",
  };
  const state = {
    working_model_snapshot: null,
    structured_model_snapshot: null,
    plantuml_snapshot: "",
    plantuml_url: "",
  };
  const assignFromEntry = (candidate) => {
    if (!candidate) return;
    const payload = candidate.payload || {};
    if (!state.working_model_snapshot) {
      state.working_model_snapshot =
        candidate.working_model_snapshot ||
        payload.model_snapshot ||
        payload.working_model ||
        null;
    }
    if (!state.structured_model_snapshot) {
      state.structured_model_snapshot =
        candidate.structured_model_snapshot ||
        payload.structured_model ||
        null;
    }
    if (!state.plantuml_snapshot) {
      state.plantuml_snapshot = candidate.plantuml_snapshot || payload.plantuml || "";
    }
    if (!state.plantuml_url) {
      state.plantuml_url = candidate.plantuml_url || payload.plantuml_url || "";
    }
  };
  assignFromEntry(entry);
  const entryIndex = traceEntries.findIndex((candidate) => candidate.id === entry.id);
  for (let index = entryIndex; index >= 0; index -= 1) {
    assignFromEntry(traceEntries[index]);
    if (
      state.working_model_snapshot
      && state.structured_model_snapshot
      && (state.plantuml_snapshot || state.plantuml_url)
    ) return state;
  }
  if (options.allowCurrentFallback && options.currentState) {
    const current = options.currentState;
    state.working_model_snapshot = state.working_model_snapshot || current.working_model_snapshot;
    state.structured_model_snapshot = state.structured_model_snapshot || current.structured_model_snapshot;
    state.plantuml_snapshot = state.plantuml_snapshot || current.plantuml_snapshot;
    state.plantuml_url = state.plantuml_url || current.plantuml_url;
  }
  return state;
}

export function traceActionEntryForCheckpoint(traceEntries = [], checkpoint, options = {}) {
  const entry = checkpoint?.entry || null;
  if (!entry) return null;
  const state = traceArtifactStateForEntry(traceEntries, entry, {
    ...options,
    allowCurrentFallback: options.allowCurrentFallback ?? checkpoint.id === "guarded-posthoc",
  });
  if (
    !state.working_model_snapshot
    && !state.structured_model_snapshot
    && !state.plantuml_snapshot
    && !state.plantuml_url
  ) return entry;
  return {
    ...entry,
    working_model_snapshot: state.working_model_snapshot || entry.working_model_snapshot || null,
    structured_model_snapshot: state.structured_model_snapshot || entry.structured_model_snapshot || null,
    plantuml_snapshot: state.plantuml_snapshot || entry.plantuml_snapshot || "",
    plantuml_url: state.plantuml_url || entry.plantuml_url || "",
  };
}
