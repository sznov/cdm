import { checkpointPresentation } from "./checkpoint_presentation.js";
import { createBuildLogTimeElement } from "./build_log_timing.js";

export function sortTranscriptCheckpoints(checkpoints = [], traceEntries = [], options = {}) {
  const traceEntrySortValue = options.traceEntrySortValue || (() => Number.MAX_SAFE_INTEGER);
  const checkpointOrderValue = options.checkpointOrderValue || (() => Number.MAX_SAFE_INTEGER);
  return [...checkpoints].sort((a, b) => {
    const aIndex = a.entry ? traceEntrySortValue(a.entry, traceEntries) : Number.MAX_SAFE_INTEGER;
    const bIndex = b.entry ? traceEntrySortValue(b.entry, traceEntries) : Number.MAX_SAFE_INTEGER;
    if (aIndex !== bIndex) return aIndex - bIndex;
    return checkpointOrderValue(a.id) - checkpointOrderValue(b.id);
  });
}

export function checkpointRowsByTraceEntry(checkpoints = []) {
  const byEntryId = new Map();
  for (const checkpoint of checkpoints) {
    const entryId = checkpoint.entry?.id || "";
    if (!entryId) continue;
    if (!byEntryId.has(entryId)) byEntryId.set(entryId, []);
    byEntryId.get(entryId).push(checkpoint);
  }
  return byEntryId;
}

export function createTranscriptCheckpointCard(checkpoint, options = {}) {
  if (!checkpoint) return null;
  const entry = checkpoint.entry;
  const row = document.createElement("article");
  row.className = "transcript-card transcript-checkpoint-card checkpoint-row";
  row.classList.toggle("is-running", checkpoint.running);
  row.classList.toggle("is-finalizing", checkpoint.finalizing);
  row.classList.toggle("is-complete", checkpoint.completed);
  row.classList.toggle("is-error", checkpoint.failed);
  row.classList.toggle("is-cancelled", checkpoint.cancelled);
  row.dataset.checkpointId = checkpoint.id || "";
  if (entry?.id) row.dataset.traceEntryId = entry.id;

  const head = document.createElement("div");
  head.className = "sequence-card-head";
  const presentation = checkpointPresentation(checkpoint);
  if (presentation.active) {
    const spinner = document.createElement("span");
    spinner.className = "phase-spinner checkpoint-spinner";
    spinner.setAttribute("aria-hidden", "true");
    head.append(spinner);
  }

  const title = document.createElement("strong");
  title.textContent = checkpoint.title;
  head.append(title);

  if (options.showTiming) {
    const timing = createBuildLogTimeElement(entry?.timestamp_utc || "", entry?.completed_at_utc || "", {
      kind: entry?.completed_at_utc ? "interval" : "event",
    });
    if (timing) {
      timing.classList.add("build-log-checkpoint-time");
      head.append(timing);
    }
  }

  const status = document.createElement("span");
  status.className = `checkpoint-status checkpoint-status-${presentation.kind}`;
  status.textContent = presentation.label;
  head.append(status);

  const summary = document.createElement("p");
  summary.className = "transcript-card-summary";
  summary.textContent = checkpoint.summary || "";
  row.append(head, summary);

  const {
    appendTraceActions,
    checkpointRetryEntry,
    inputOutputTraceEntryForCheckpoint,
    traceActionEntryForCheckpoint,
  } = options;
  if (entry && appendTraceActions && traceActionEntryForCheckpoint) {
    const checkpointIncomplete = checkpoint.running || checkpoint.finalizing || !checkpoint.completed;
    appendTraceActions(row, traceActionEntryForCheckpoint(checkpoint), {
      forceDisableOutput: checkpoint.running || checkpoint.finalizing,
      forceDisableArtifacts: checkpointIncomplete,
      inputOutputEntry: inputOutputTraceEntryForCheckpoint?.(checkpoint),
      retryEntry: checkpointRetryEntry?.(checkpoint),
      retryContext: { checkpointId: checkpoint.id, checkpointTitle: checkpoint.title },
      showRetry: checkpoint.id !== "guarded-posthoc",
    });
  }

  return row;
}

export function appendTranscriptCheckpointCard(container, checkpoint, options = {}) {
  if (!container || !checkpoint) return null;
  const row = createTranscriptCheckpointCard(checkpoint, options);
  if (!row) return null;
  container.append(row);
  return row;
}
