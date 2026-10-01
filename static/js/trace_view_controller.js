import {
  appendTraceActionsView,
  applyModelToolbarIconsView,
} from './trace_actions.js';
import { traceActionDefinitions } from './trace_action_definitions.js';
import {
  renderSequenceView,
  renderTraceInspectorView,
  updateTraceInspectorDetailView,
} from './trace_progress_view.js';
import { selectedTraceEntry } from './trace_retry_controls.js';
export {
  canRetryFromTraceEntry,
  selectedTraceEntry,
  traceRetryDisabledReason,
  updateRetryRunControls,
} from './trace_retry_controls.js';
export { traceActionDefinitions } from './trace_action_definitions.js';

export function jumpToCurrentTrace(context) {
  context.setAutoFollowTrace(true);
  const latest = context.latestVisibleTraceEntry();
  context.setSelectedTraceId(latest?.id || null);
  if (context.selectedTraceId()) context.setRightRailTab("progress");
  renderSequence(context);
  if (context.elements.sequenceTimeline) context.elements.sequenceTimeline.scrollTop = 0;
  renderTraceInspector(context);
}

export function applyModelToolbarIcons(context) {
  applyModelToolbarIconsView(context.elements, {
    updateDiagramControlState: context.updateDiagramControlState,
    scheduleHeaderOverflowUpdate: context.scheduleHeaderOverflowUpdate,
  });
}

export function appendTraceActions(context, container, entry, options = {}) {
  appendTraceActionsView(container, entry, traceActionDefinitions(context, entry, options), {
    onSelect: (selectionEntry) => {
      context.setSelectedTraceId(selectionEntry.id);
      const entries = context.traceEntries();
      context.setAutoFollowTrace(selectionEntry.id === entries[entries.length - 1]?.id);
      renderSequence(context);
      renderTraceInspector(context);
    },
  });
}

export function renderSequence(context) {
  renderSequenceView({
    elements: context.elements,
    traceEntries: context.traceEntries(),
    progressRows: context.workflowProgressRows(),
    traceLoadingRunId: context.traceLoadingRunId(),
    selectedRunId: context.selectedRunId(),
    selectedTraceId: context.selectedTraceId(),
    autoFollowTrace: context.autoFollowTrace(),
    onEntrySelected: (entry) => {
      context.setSelectedTraceId(entry.id);
      const entries = context.traceEntries();
      context.setAutoFollowTrace(entry.id === entries[entries.length - 1]?.id);
      context.setRightRailTab("progress");
      renderSequence(context);
      renderTraceInspector(context);
    },
    appendCheckpointActions: (card, checkpoint) => {
      const checkpointIncomplete = checkpoint.running || !checkpoint.completed;
      appendTraceActions(context, card, context.traceActionEntryForCheckpoint(checkpoint), {
        forceDisableOutput: checkpoint.running,
        forceDisableArtifacts: checkpointIncomplete,
        retryEntry: context.checkpointRetryEntry(checkpoint),
        retryContext: { checkpointId: checkpoint.id, checkpointTitle: checkpoint.title },
        showRetry: checkpoint.id !== "guarded-posthoc",
      });
    },
  });
}

export function updateTraceInspectorDetail(context, title, value) {
  updateTraceInspectorDetailView({
    elements: context.elements,
    title,
    value,
    renderTraceInspector: () => renderTraceInspector(context),
    setScrollableText: context.setScrollableText,
  });
}

export function renderTraceInspector(context) {
  const entry = selectedTraceEntry(context);
  renderTraceInspectorView({
    elements: context.elements,
    traceEntries: context.traceEntries(),
    selectedTraceId: context.selectedTraceId(),
    autoFollowTrace: context.autoFollowTrace(),
    latestEntry: context.latestVisibleTraceEntry(),
    actions: entry ? traceActionDefinitions(context, entry) : [],
  });
}
