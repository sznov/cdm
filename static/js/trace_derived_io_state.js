import { inputOutputTraceEntryForCheckpoint as progressInputOutputTraceEntryForCheckpoint } from './progress_trace.js';
import {
  stepInputForTraceEntry as traceStepInputForTraceEntry,
  stepOutputForTraceEntry as traceStepOutputForTraceEntry,
  traceEntryHasInputOrOutput as traceEntryHasInputOrOutputValue,
} from './trace_io.js';

export function traceInputOutputContext(context) {
  return {
    traceEntries: context.traceEntries(),
    specification: context.specification(),
  };
}

export function traceEntryHasInputOrOutput(context, entry) {
  return traceEntryHasInputOrOutputValue(entry, traceInputOutputContext(context));
}

export function inputOutputTraceEntryForCheckpoint(context, checkpoint) {
  return progressInputOutputTraceEntryForCheckpoint(
    context.traceEntries(),
    checkpoint,
    (entry) => traceEntryHasInputOrOutput(context, entry)
  );
}

export function stepInputForTraceEntry(context, entry) {
  return traceStepInputForTraceEntry(entry, traceInputOutputContext(context));
}

export function stepOutputForTraceEntry(context, entry) {
  return traceStepOutputForTraceEntry(entry, traceInputOutputContext(context));
}
