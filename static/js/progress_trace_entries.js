import {
  isDirectBaselineEntry,
  isPosthocTraceEvent,
} from "./progress_checkpoints.js";

export function firstAcceptedDraftEntry(traceEntries = []) {
  return traceEntries.find(
    (entry) => entry.event === "draft_model_validation" && (entry.status === "accepted" || entry.payload?.accepted)
  ) || null;
}

export function mainPatchResultEntry(traceEntries = []) {
  const firstPosthocIndex = traceEntries.findIndex(isPosthocTraceEvent);
  const searchEnd = firstPosthocIndex >= 0 ? firstPosthocIndex : traceEntries.length;
  for (let index = searchEnd - 1; index >= 0; index -= 1) {
    const entry = traceEntries[index];
    if (entry?.event === "structured_model_validated") return entry;
    if (entry?.event === "partial_model_snapshot" && entry?.payload?.summary === "Rendered after post-patch language repair.") {
      return entry;
    }
  }
  return traceEntries.find((entry) => entry.event === "done") || null;
}

export function directBaselineResultEntry(traceEntries = []) {
  for (let index = traceEntries.length - 1; index >= 0; index -= 1) {
    const entry = traceEntries[index];
    if (!isDirectBaselineEntry(entry)) continue;
    if (entry.event === "direct_baseline_validation" && (entry.status === "accepted" || entry.payload?.accepted)) return entry;
    if (entry.event === "structured_model_validated") return entry;
    if (entry.event === "done") return entry;
  }
  return null;
}

export function latestResumeCheckpointEntry(traceEntries = []) {
  for (let index = traceEntries.length - 1; index >= 0; index -= 1) {
    const entry = traceEntries[index];
    if (entry?.event === "resume_from_checkpoint") return entry;
  }
  return null;
}

export function guardedPosthocResultEntry(traceEntries = []) {
  let posthocStarted = false;
  for (let index = 0; index < traceEntries.length; index += 1) {
    const entry = traceEntries[index];
    if (isPosthocTraceEvent(entry)) posthocStarted = true;
    if (entry.event === "correction_sequence_done" || entry.event === "correction_patch_chat_done") return entry;
    if (posthocStarted && entry.event === "done") return entry;
  }
  return null;
}

export function guardedPosthocFinalizationEntry(traceEntries = []) {
  const finalizingEvents = new Set([
    "correction_patch_generation_done",
    "correction_sequence_step_done",
  ]);
  for (let index = traceEntries.length - 1; index >= 0; index -= 1) {
    const entry = traceEntries[index];
    if (finalizingEvents.has(entry.event)) return entry;
    if (
      entry.event === "checkpoint_written" &&
      entry.payload?.stage === "structured-patch-posthoc-correction"
    ) {
      return entry;
    }
  }
  return null;
}

export function terminalRunEntry(traceEntries = []) {
  for (let index = traceEntries.length - 1; index >= 0; index -= 1) {
    const entry = traceEntries[index];
    if (entry.event === "error" || entry.event === "cancelled") return entry;
  }
  return null;
}
