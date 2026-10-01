import { workflowProgressCheckpointIdForEntry } from './progress_checkpoints.js';
import { workflowProgressRows } from './trace_derived_progress_state.js';

export function traceEntryVisibleForProgressFilter(entry) {
  return Boolean(workflowProgressCheckpointIdForEntry(entry)) ||
    ["error", "cancelled"].includes(String(entry?.event || ""));
}

export function latestVisibleTraceEntry(context) {
  const firstProgressRow = workflowProgressRows(context)[0];
  if (firstProgressRow?.entry) return firstProgressRow.entry;
  const entries = context.traceEntries();
  return entries[entries.length - 1] || null;
}

export function ensureTraceEntryRendered(context, entryId) {
  if (!entryId) return;
  let visibleOffset = 0;
  const entries = context.traceEntries();
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const entry = entries[index];
    if (!traceEntryVisibleForProgressFilter(entry)) continue;
    if (entry.id === entryId) {
      if (visibleOffset >= context.traceRenderLimit()) context.setTraceRenderLimit(visibleOffset + 1);
      return;
    }
    visibleOffset += 1;
  }
}
