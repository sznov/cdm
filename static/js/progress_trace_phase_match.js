import {
  checkpointIdForResumeStage,
  isDirectBaselineEntry,
  isPosthocTraceEvent,
} from "./progress_checkpoints.js";

export function latestTraceEntryForCheckpointPhase(traceEntries = [], checkpointId) {
  for (let index = traceEntries.length - 1; index >= 0; index -= 1) {
    const entry = traceEntries[index];
    const event = String(entry.event || "");
    if (event === "resume_from_checkpoint" && checkpointIdForResumeStage(entry.payload?.stage) === checkpointId) return entry;
    if (checkpointId === "direct-baseline-result" && isDirectBaselineEntry(entry)) return entry;
    if (checkpointId === "guarded-posthoc" && isPosthocTraceEvent(entry)) return entry;
    if (
      checkpointId === "structured-patch-result" &&
      !isPosthocTraceEvent(entry) &&
      (
        event.includes("structured_language") ||
        event.includes("coverage_critic") ||
        event.includes("patch_operation") ||
        event.includes("structured_patch")
      )
    ) {
      return entry;
    }
    if (
      checkpointId === "first-valid-draft" &&
      (event.includes("draft_model") || event === "start" || event === "model_call_log")
    ) {
      return entry;
    }
  }
  return traceEntries[traceEntries.length - 1] || null;
}

export function traceEntryMatchesCheckpointPhase(checkpointId, entry) {
  const event = String(entry?.event || "");
  if (event === "resume_from_checkpoint") return checkpointIdForResumeStage(entry?.payload?.stage) === checkpointId;
  if (checkpointId === "direct-baseline-result") return isDirectBaselineEntry(entry);
  if (checkpointId === "guarded-posthoc") return isPosthocTraceEvent(entry);
  if (checkpointId === "structured-patch-result") {
    return (
      !isPosthocTraceEvent(entry) &&
      (
        event === "done" ||
        event.includes("structured_language") ||
        event.includes("coverage_critic") ||
        event.includes("patch_operation") ||
        event.includes("structured_patch")
      )
    );
  }
  if (checkpointId === "first-valid-draft") {
    return event.includes("draft_model") || event === "start" || event === "model_call_log";
  }
  return false;
}
