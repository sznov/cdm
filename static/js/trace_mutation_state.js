export function isStatefulTraceEntry(entry) {
  return Boolean(entry && !["start", "error"].includes(entry.event));
}

export function attachCurrentStateToEntry(context, entry) {
  if (!entry || !isStatefulTraceEntry(entry)) return;
  Object.assign(entry, context.currentModelSnapshot());
}

export function attachCurrentStateToRecentTrace(context) {
  if (context.loadingArchivedRun()) return;
  for (let index = context.traceEntries().length - 1; index >= 0; index -= 1) {
    const entry = context.traceEntries()[index];
    if (!isStatefulTraceEntry(entry)) continue;
    attachCurrentStateToEntry(context, entry);
    if (context.selectedTraceId() === entry.id) context.renderTraceInspector();
    context.renderSequence();
    return;
  }
}
