import { isNonCheckpointRetryEntry } from './trace_status.js';
import { runActionBlocked } from './state.js';

const CHECKPOINT_BRANCHABLE_EXECUTORS = new Set([
  "structured_patch_legacy",
  "structured_patch_refined",
]);

export function selectedTraceEntry(context) {
  return context.traceEntries().find((candidate) => candidate.id === context.selectedTraceId()) || null;
}

export function traceRetryDisabledReason(context, entry = selectedTraceEntry(context)) {
  if (!entry) return "Select a trace row first.";
  if (!context.selectedRunId()) return "Select a run first.";
  if (runActionBlocked(context.selectedRunId())) {
    return "Wait for the current operation on this run before branching from a checkpoint.";
  }
  const runRecord = context.selectedRunRecord();
  const executorId = runRecord?.effective_harness_run_spec?.executor_id || "";
  if (!CHECKPOINT_BRANCHABLE_EXECUTORS.has(executorId)) {
    return "Checkpoint branching is only available for application-runnable structured-patch harnesses.";
  }
  if (isNonCheckpointRetryEntry(entry)) return "This lifecycle row is not retryable. Pick the last model/checkpoint row before it.";
  const index = Number(entry.trace_index);
  if (!Number.isInteger(index) || index < 0) return "This trace row has no stable trace index.";
  const hasPriorCheckpoint = context.traceEntries().some(
    (candidate) => Number(candidate.trace_index) <= index && candidate.working_model_snapshot
  );
  if (!hasPriorCheckpoint) return "No structured-model checkpoint exists at or before this trace row.";
  return "";
}

export function canRetryFromTraceEntry(context, entry = selectedTraceEntry(context)) {
  return !traceRetryDisabledReason(context, entry);
}

export function updateRetryRunControls(context) {
  const selected = context.selectedRunRecord();
  const retryButton = context.elements.retryRunButton;
  if (retryButton) {
    retryButton.disabled = runActionBlocked(selected?.job_id) || !selected;
    retryButton.title = selected
      ? "Start a new run using this archived run's harness/provider/config and the current specification text."
      : "Select a run first.";
  }
  const resumeButton = context.elements.resumeRunButton;
  if (resumeButton) {
    const resumable = Boolean(selected?.resumable);
    const checkpointStage = selected?.resume_checkpoint_stage || "";
    resumeButton.disabled = runActionBlocked(selected?.job_id) || !selected || !resumable || !checkpointStage;
    resumeButton.title = !selected
      ? "Select a run first."
      : !resumable
      ? "Selected run is not resumable."
      : checkpointStage
      ? `Start a new run from checkpoint: ${checkpointStage}.`
      : "Selected run has no sane checkpoint to resume from.";
  }
}
