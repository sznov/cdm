import { traceDerivedStateContext } from './trace_derived_context.js';
import {
  ensureTraceEntryRendered as ensureTraceEntryRenderedWithContext,
  guardedPosthocResultEntry as guardedPosthocResultEntryWithContext,
  latestVisibleTraceEntry as latestVisibleTraceEntryWithContext,
  workflowProgressRows as workflowProgressRowsWithContext,
  traceActionEntryForCheckpoint as traceActionEntryForCheckpointWithContext,
  traceEntryVisibleForProgressFilter as traceEntryVisibleForProgressFilterValue,
} from './trace_derived_state.js';

export function traceEntryVisibleForProgressFilter(_context, entry) {
  return traceEntryVisibleForProgressFilterValue(entry);
}

export function latestVisibleTraceEntry(context) {
  return latestVisibleTraceEntryWithContext(traceDerivedStateContext(context));
}

export function traceRenderingDeferred(context) {
  return context.state.loadingArchivedRun;
}

export function ensureTraceEntryRendered(context, entryId) {
  return ensureTraceEntryRenderedWithContext(traceDerivedStateContext(context), entryId);
}

export function guardedPosthocResultEntry(context) {
  return guardedPosthocResultEntryWithContext(traceDerivedStateContext(context));
}

export function traceActionEntryForCheckpoint(context, checkpoint) {
  return traceActionEntryForCheckpointWithContext(traceDerivedStateContext(context), checkpoint);
}

export function workflowProgressRows(context) {
  return workflowProgressRowsWithContext(traceDerivedStateContext(context));
}
