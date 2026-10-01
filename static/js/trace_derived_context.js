import {
  runOperationPending,
  selectedPresentationTrace,
  selectedWorkingModel,
} from './state.js';

export function traceDerivedStateContext(context) {
  const { elements, state } = context;
  return {
    appendTraceActions: context.appendTraceActions,
    checkpointRetryEntry: context.checkpointRetryEntry,
    currentModelSnapshot: context.currentModelSnapshot,
    currentWorkingModel: selectedWorkingModel,
    isActive: () => runOperationPending(state.selectedRunId) || context.selectedRunIsActive(),
    runtimeHarness: () => state.runtimeHarness,
    specification: () => state.currentSession?.specification || elements.specification?.value?.trim() || "",
    setTraceRenderLimit: (limit) => {
      state.traceRenderLimit = limit;
    },
    traceEntries: selectedPresentationTrace,
    traceRenderLimit: () => state.traceRenderLimit,
    unifiedChatLog: () => elements.unifiedChatLog,
  };
}
