export function selectedRunId(context) {
  return context.selectedRunId?.() || "";
}

export function ensureSelectedRunId(context) {
  return selectedRunId(context);
}
