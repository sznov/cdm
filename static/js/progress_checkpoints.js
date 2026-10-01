import {
  checkpointCounts,
  checkpointOperationCounts,
} from "./progress_checkpoint_counts.js";

export {
  DIRECT_BASELINE_PROGRESS_CHECKPOINTS,
  WORKFLOW_PROGRESS_CHECKPOINTS,
  checkpointIdForResumeStage,
  checkpointOrderValue,
  isDirectBaselineEntry,
  isDirectBaselineHarness,
  isPosthocTraceEvent,
  workflowProgressCheckpointIdForEntry,
  progressCheckpointsForRuntime,
} from "./progress_checkpoint_defs.js";

export {
  checkpointCounts,
  checkpointOperationCounts,
  modelCountsFromSnapshot,
  numericPayloadValue,
} from "./progress_checkpoint_counts.js";

export function checkpointSummary(definition, entry, running, modelSnapshotForEntry = () => null, finalizing = false) {
  if (running) return "Running";
  if (finalizing) return definition.finalizingSummary || "Finalizing";
  const modelCounts = checkpointCounts(entry, modelSnapshotForEntry);
  const operationCounts = checkpointOperationCounts(entry);
  const lines = [];
  if (modelCounts) {
    lines.push(`${modelCounts.entities} entities, ${modelCounts.attributes} attributes, ${modelCounts.relationships} relationships`);
  }
  if (operationCounts) {
    lines.push(`${operationCounts.accepted} accepted, ${operationCounts.rejected} rejected`);
  }
  return lines.join("\n") || entry?.summary || definition.fallbackSummary;
}
