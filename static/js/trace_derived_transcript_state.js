import { checkpointOrderValue } from './progress_checkpoints.js';
import { traceEntrySortValue } from './trace_transcript.js';
import {
  appendTranscriptCheckpointCard as appendTranscriptCheckpointCardElement,
  createTranscriptCheckpointCard as createTranscriptCheckpointCardElement,
  sortTranscriptCheckpoints,
} from './transcript_checkpoints.js';
import { inputOutputTraceEntryForCheckpoint } from './trace_derived_io_state.js';
import {
  workflowProgressRows,
  traceActionEntryForCheckpoint,
} from './trace_derived_progress_state.js';

export function sortedTranscriptCheckpoints(context) {
  return sortTranscriptCheckpoints(workflowProgressRows(context), context.traceEntries(), {
    checkpointOrderValue,
    traceEntrySortValue,
  });
}

export function transcriptCheckpointActionOptions(context) {
  return {
    appendTraceActions: context.appendTraceActions,
    checkpointRetryEntry: context.checkpointRetryEntry,
    inputOutputTraceEntryForCheckpoint: (checkpoint) => inputOutputTraceEntryForCheckpoint(context, checkpoint),
    traceActionEntryForCheckpoint: (checkpoint) => traceActionEntryForCheckpoint(context, checkpoint),
  };
}

export function createTranscriptCheckpointCard(context, checkpoint, viewOptions = {}) {
  return createTranscriptCheckpointCardElement(checkpoint, {
    ...transcriptCheckpointActionOptions(context),
    ...viewOptions,
  });
}

export function appendTranscriptCheckpointCard(context, checkpoint) {
  return appendTranscriptCheckpointCardElement(
    context.unifiedChatLog(),
    checkpoint,
    transcriptCheckpointActionOptions(context)
  );
}
