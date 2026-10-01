export const WORKFLOW_PROGRESS_CHECKPOINTS = [
  {
    id: "guarded-posthoc",
    title: "Final draft",
    agent: "Guarded correction",
    runningSummary: "Applying the guarded single post-hoc correction pass.",
    finalizingSummary: "Revision received; saving the final checkpoint.",
    fallbackSummary: "Final checkpoint after the guarded post-hoc correction pass.",
  },
  {
    id: "structured-patch-result",
    title: "Revised draft",
    agent: "Patch loop",
    runningSummary: "Critiquing and applying structured patch operations.",
    fallbackSummary: "Main harness checkpoint before the guarded post-hoc correction pass.",
  },
  {
    id: "first-valid-draft",
    title: "First draft",
    agent: "Draft modeler",
    runningSummary: "Generating and validating the first structured draft.",
    fallbackSummary: "First draft that passed schema and link validation.",
  },
];

export const DIRECT_BASELINE_PROGRESS_CHECKPOINTS = [
  {
    id: "direct-baseline-result",
    title: "Direct baseline",
    agent: "Direct baseline",
    runningSummary: "Generating and validating one direct structured model.",
    fallbackSummary: "Single-call direct baseline result.",
  },
];

export function isDirectBaselineHarness(runtimeHarness) {
  const id = String(runtimeHarness?.id || runtimeHarness || "");
  return runtimeHarness?.family === "direct_baseline" || id.startsWith("direct-baseline");
}

export function isDirectBaselineEntry(entry) {
  if (!entry) return false;
  if (isDirectBaselineHarness(entry.runtime_harness_id || entry.payload?.runtime_harness_id)) return true;
  if (String(entry.agent_id || entry.payload?.agent_id || "") === "directBaseline") return true;
  const event = String(entry.event || "");
  return event.startsWith("direct_baseline_") || entry.payload?.direct_baseline === true;
}

export function progressCheckpointsForRuntime(runtimeHarness, traceEntries = []) {
  if (isDirectBaselineHarness(runtimeHarness) || traceEntries.some(isDirectBaselineEntry)) {
    return DIRECT_BASELINE_PROGRESS_CHECKPOINTS;
  }
  return WORKFLOW_PROGRESS_CHECKPOINTS;
}

export function checkpointIdForResumeStage(stage) {
  const value = String(stage || "");
  if (value === "async-op-patch-after-patch-operations") return "structured-patch-result";
  if (value === "direct_baseline_final") return "direct-baseline-result";
  if (value.startsWith("async-op-patch-")) return "first-valid-draft";
  return "";
}

export function isPosthocTraceEvent(entry) {
  return String(entry?.event || "").startsWith("correction_");
}

export function workflowProgressCheckpointIdForEntry(entry) {
  if (!entry) return "";
  if (isDirectBaselineEntry(entry)) return "direct-baseline-result";
  if (entry.event === "resume_from_checkpoint") {
    return checkpointIdForResumeStage(entry.payload?.stage);
  }
  if (entry.event === "draft_model_validation" && (entry.status === "accepted" || entry.payload?.accepted)) {
    return "first-valid-draft";
  }
  if (entry.event === "done") return "structured-patch-result";
  if (entry.event === "correction_sequence_done" || entry.event === "correction_patch_chat_done") {
    return "guarded-posthoc";
  }
  return "";
}

export function checkpointOrderValue(checkpointId) {
  if (checkpointId === "direct-baseline-result") return 1;
  if (checkpointId === "first-valid-draft") return 1;
  if (checkpointId === "structured-patch-result") return 2;
  if (checkpointId === "guarded-posthoc") return 3;
  return 99;
}
