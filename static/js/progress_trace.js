import {
  WORKFLOW_PROGRESS_CHECKPOINTS,
  checkpointIdForResumeStage,
  checkpointSummary,
  isDirectBaselineEntry,
  isDirectBaselineHarness,
  progressCheckpointsForRuntime,
} from "./progress_checkpoints.js";
import {
  directBaselineResultEntry,
  firstAcceptedDraftEntry,
  guardedPosthocFinalizationEntry,
  guardedPosthocResultEntry,
  latestResumeCheckpointEntry,
  mainPatchResultEntry,
  terminalRunEntry,
} from "./progress_trace_entries.js";
import {
  activeWorkflowCheckpointId,
  latestTraceEntryForCheckpointPhase,
  terminalCheckpointId,
} from "./progress_trace_phase.js";
export {
  directBaselineResultEntry,
  firstAcceptedDraftEntry,
  guardedPosthocFinalizationEntry,
  guardedPosthocResultEntry,
  latestResumeCheckpointEntry,
  mainPatchResultEntry,
  terminalRunEntry,
} from "./progress_trace_entries.js";
export {
  activeWorkflowCheckpointId,
  inputOutputTraceEntryForCheckpoint,
  latestTraceEntryForCheckpointPhase,
  terminalCheckpointId,
  traceEntryMatchesCheckpointPhase,
} from "./progress_trace_phase.js";

export function workflowProgressRows(traceEntries = [], options = {}) {
  if (isDirectBaselineHarness(options.runtimeHarness) || traceEntries.some(isDirectBaselineEntry)) {
    const definition = progressCheckpointsForRuntime(options.runtimeHarness, traceEntries)[0];
    const completedEntry = directBaselineResultEntry(traceEntries);
    const terminalEntry = terminalRunEntry(traceEntries);
    const terminal = Boolean(terminalEntry && !completedEntry);
    const running = Boolean(options.isActive && !completedEntry && !terminal);
    if (!completedEntry && !running && !terminal) return [];
    const entry = terminal
      ? terminalEntry
      : completedEntry || latestTraceEntryForCheckpointPhase(traceEntries, definition.id);
    return [{
      ...definition,
      entry,
      running,
      terminal,
      failed: terminal && terminalEntry?.event === "error",
      cancelled: terminal && terminalEntry?.event === "cancelled",
      completed: Boolean(completedEntry),
      summary: terminal
        ? entry?.summary || entry?.payload?.detail || entry?.payload?.message || "Run stopped before this checkpoint completed."
        : checkpointSummary(definition, completedEntry || entry, running, options.modelSnapshotForEntry),
    }];
  }
  const resumeEntry = latestResumeCheckpointEntry(traceEntries);
  const resumeCheckpointId = checkpointIdForResumeStage(resumeEntry?.payload?.stage);
  const entries = {
    draftEntry: firstAcceptedDraftEntry(traceEntries) || (resumeCheckpointId === "first-valid-draft" ? resumeEntry : null),
    mainEntry: mainPatchResultEntry(traceEntries) || (resumeCheckpointId === "structured-patch-result" ? resumeEntry : null),
    posthocEntry: guardedPosthocResultEntry(traceEntries),
    posthocFinalizationEntry: guardedPosthocFinalizationEntry(traceEntries),
  };
  const activeCheckpointId = activeWorkflowCheckpointId(traceEntries, entries, Boolean(options.isActive));
  const terminalEntry = terminalRunEntry(traceEntries);
  const terminalCheckpoint = terminalCheckpointId(traceEntries, entries);
  const entryByCheckpoint = {
    "first-valid-draft": entries.draftEntry,
    "structured-patch-result": entries.mainEntry,
    "guarded-posthoc": entries.posthocEntry,
  };
  return WORKFLOW_PROGRESS_CHECKPOINTS.map((definition) => {
    const completedEntry = entryByCheckpoint[definition.id] || null;
    const finalizingEntry = definition.id === "guarded-posthoc" ? entries.posthocFinalizationEntry : null;
    const finalizing = Boolean(
      options.isActive &&
      finalizingEntry &&
      !completedEntry &&
      activeCheckpointId === definition.id
    );
    const running = activeCheckpointId === definition.id && !completedEntry && !finalizing;
    const terminal = terminalCheckpoint === definition.id && !completedEntry && !running && !finalizing;
    if (!completedEntry && !running && !finalizing && !terminal) return null;
    const entry = terminal
      ? terminalEntry
      : completedEntry || finalizingEntry || latestTraceEntryForCheckpointPhase(traceEntries, definition.id);
    return {
      ...definition,
      entry,
      running,
      finalizing,
      terminal,
      failed: terminal && terminalEntry?.event === "error",
      cancelled: terminal && terminalEntry?.event === "cancelled",
      completed: Boolean(completedEntry),
      summary: terminal
        ? entry?.summary || entry?.payload?.detail || entry?.payload?.message || "Run stopped before this checkpoint completed."
        : checkpointSummary(definition, completedEntry || entry, running, options.modelSnapshotForEntry, finalizing),
    };
  }).filter(Boolean);
}
