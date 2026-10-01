export function finalSnapshotPayloadFromTrace(trace = []) {
  for (let index = trace.length - 1; index >= 0; index -= 1) {
    const payload = trace[index]?.payload || {};
    if (payload.model_snapshot || payload.structured_model || payload.plantuml) {
      return {
        model_snapshot: payload.model_snapshot,
        structured_model: payload.structured_model,
        plantuml: payload.plantuml,
        diagram_version: payload.diagram_version,
      };
    }
  }
  return null;
}

export function checkpointRetryEntry(checkpoint) {
  if (!checkpoint || checkpoint.id === "guarded-posthoc") return null;
  return checkpoint.entry || null;
}

export function normalizedTraceIndex(value) {
  const index = Number(value);
  return Number.isInteger(index) && index >= 0 ? index : null;
}
