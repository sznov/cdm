import { selectedPresentationTrace } from './state.js';

export function traceViewControllerContext(context) {
  const { state } = context;
  return {
    elements: context.elements,
    autoFollowTrace: () => state.autoFollowTrace,
    checkpointRetryEntry: context.checkpointRetryEntry,
    latestVisibleTraceEntry: context.latestVisibleTraceEntry,
    openTextModal: context.openTextModal,
    workflowProgressRows: context.workflowProgressRows,
    retryFromTraceStep: context.retryFromTraceStep,
    scheduleHeaderOverflowUpdate: context.scheduleHeaderOverflowUpdate,
    selectedRunId: () => state.selectedRunId,
    selectedRunRecord: context.selectedRunRecord,
    selectedTraceId: () => state.selectedTraceId,
    setAutoFollowTrace: (follow) => {
      state.autoFollowTrace = Boolean(follow);
    },
    setRightRailTab: context.setRightRailTab,
    setScrollableText: context.setScrollableText,
    setSelectedTraceId: (traceId) => {
      state.selectedTraceId = traceId || null;
    },
    setStatus: context.setStatus,
    stepInputForTraceEntry: context.stepInputForTraceEntry,
    stepOutputForTraceEntry: context.stepOutputForTraceEntry,
    traceActionEntryForCheckpoint: context.traceActionEntryForCheckpoint,
    traceEntries: selectedPresentationTrace,
    traceLoadingRunId: () => state.traceLoadingRunId,
    updateDiagramControlState: context.updateDiagramControlState,
  };
}
