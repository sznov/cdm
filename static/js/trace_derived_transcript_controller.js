import { traceDerivedStateContext } from './trace_derived_context.js';
import {
  appendTranscriptCheckpointCard as appendTranscriptCheckpointCardWithContext,
  createTranscriptCheckpointCard as createTranscriptCheckpointCardWithContext,
  inputOutputTraceEntryForCheckpoint as inputOutputTraceEntryForCheckpointWithContext,
  sortedTranscriptCheckpoints as sortedTranscriptCheckpointsWithContext,
  stepInputForTraceEntry as stepInputForTraceEntryWithContext,
  stepOutputForTraceEntry as stepOutputForTraceEntryWithContext,
  traceEntryHasInputOrOutput as traceEntryHasInputOrOutputWithContext,
  transcriptCheckpointActionOptions as transcriptCheckpointActionOptionsWithContext,
} from './trace_derived_state.js';

export function traceEntryHasInputOrOutput(context, entry) {
  return traceEntryHasInputOrOutputWithContext(traceDerivedStateContext(context), entry);
}

export function inputOutputTraceEntryForCheckpoint(context, checkpoint) {
  return inputOutputTraceEntryForCheckpointWithContext(traceDerivedStateContext(context), checkpoint);
}

export function stepInputForTraceEntry(context, entry) {
  return stepInputForTraceEntryWithContext(traceDerivedStateContext(context), entry);
}

export function stepOutputForTraceEntry(context, entry) {
  return stepOutputForTraceEntryWithContext(traceDerivedStateContext(context), entry);
}

export function sortedTranscriptCheckpoints(context) {
  return sortedTranscriptCheckpointsWithContext(traceDerivedStateContext(context));
}

export function transcriptCheckpointActionOptions(context) {
  return transcriptCheckpointActionOptionsWithContext(traceDerivedStateContext(context));
}

export function createTranscriptCheckpointCard(context, checkpoint, viewOptions = {}) {
  return createTranscriptCheckpointCardWithContext(traceDerivedStateContext(context), checkpoint, viewOptions);
}

export function appendTranscriptCheckpointCard(context, checkpoint) {
  return appendTranscriptCheckpointCardWithContext(traceDerivedStateContext(context), checkpoint);
}
