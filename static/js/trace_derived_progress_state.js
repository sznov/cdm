import {
  guardedPosthocResultEntry as progressGuardedPosthocResultEntry,
  workflowProgressRows as deriveWorkflowProgressRows,
} from './progress_trace.js';
import {
  modelSnapshotForCheckpointEntry as artifactModelSnapshotForCheckpointEntry,
  traceActionEntryForCheckpoint as artifactTraceActionEntryForCheckpoint,
} from './model_artifacts.js';

export function guardedPosthocResultEntry(context) {
  return progressGuardedPosthocResultEntry(context.traceEntries());
}

export function modelSnapshotForCheckpointEntry(context, entry) {
  return artifactModelSnapshotForCheckpointEntry(context.traceEntries(), entry, context.currentWorkingModel());
}

export function traceActionEntryForCheckpoint(context, checkpoint) {
  if (!checkpoint?.completed && checkpoint?.entry) {
    return {
      ...checkpoint.entry,
      working_model_snapshot: null,
      structured_model_snapshot: null,
      plantuml_snapshot: "",
      plantuml_url: "",
    };
  }
  return artifactTraceActionEntryForCheckpoint(context.traceEntries(), checkpoint, {
    currentState: context.currentModelSnapshot(),
    allowCurrentFallback: Boolean(checkpoint?.completed && checkpoint?.id === "guarded-posthoc"),
  });
}

export function workflowProgressRows(context) {
  return deriveWorkflowProgressRows(context.traceEntries(), {
    isActive: context.isActive(),
    modelSnapshotForEntry: (entry) => modelSnapshotForCheckpointEntry(context, entry),
    runtimeHarness: context.runtimeHarness(),
  });
}
