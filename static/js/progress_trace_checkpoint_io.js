import { isModelCallTraceEvent } from "./trace_status.js";
import { traceEntryMatchesCheckpointPhase } from "./progress_trace_phase_match.js";

export function inputOutputTraceEntryForCheckpoint(traceEntries = [], checkpoint, hasInputOrOutput = () => false) {
  const entry = checkpoint?.entry || null;
  if (!entry) return null;

  const entryIndex = traceEntries.findIndex((candidate) => candidate.id === entry.id);
  if (entryIndex < 0) return entry;

  for (let index = entryIndex - 1; index >= 0; index -= 1) {
    const candidate = traceEntries[index];
    if (!traceEntryMatchesCheckpointPhase(checkpoint.id, candidate)) continue;
    if (isModelCallTraceEvent(candidate) && hasInputOrOutput(candidate)) return candidate;
  }
  if (hasInputOrOutput(entry)) return entry;
  for (let index = entryIndex - 1; index >= 0; index -= 1) {
    const candidate = traceEntries[index];
    if (!traceEntryMatchesCheckpointPhase(checkpoint.id, candidate)) continue;
    if (hasInputOrOutput(candidate)) return candidate;
  }
  return entry;
}
