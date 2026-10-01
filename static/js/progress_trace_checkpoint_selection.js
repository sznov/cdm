import { isPosthocTraceEvent } from "./progress_checkpoints.js";
import {
  firstAcceptedDraftEntry,
  guardedPosthocResultEntry,
  mainPatchResultEntry,
  terminalRunEntry,
} from "./progress_trace_entries.js";

export function terminalCheckpointId(traceEntries = [], entries = {}) {
  const terminalEntry = terminalRunEntry(traceEntries);
  if (!terminalEntry) return "";
  if (!entries.draftEntry) return "first-valid-draft";
  if (traceEntries.some(isPosthocTraceEvent) && !entries.posthocEntry) return "guarded-posthoc";
  if (!entries.mainEntry) return "structured-patch-result";
  return "guarded-posthoc";
}

export function activeWorkflowCheckpointId(traceEntries = [], entries = {}, isActive = false) {
  if (!isActive) return "";
  const draftEntry = entries.draftEntry || firstAcceptedDraftEntry(traceEntries);
  const mainEntry = entries.mainEntry || mainPatchResultEntry(traceEntries);
  const posthocEntry = entries.posthocEntry || guardedPosthocResultEntry(traceEntries);
  if (posthocEntry) return "";
  if (traceEntries.some(isPosthocTraceEvent)) return "guarded-posthoc";
  if (mainEntry) return "";
  if (draftEntry) return "structured-patch-result";
  return "first-valid-draft";
}
