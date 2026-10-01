import {
  selectRun,
  selectedPlantuml,
  selectedPlantumlUrl,
  selectedPresentationTrace,
  selectedStructuredModel,
  selectedWorkingModel,
  setRunOutput,
  setRunPlantuml,
  setRunPlantumlUrl,
  setRunPresentationTrace,
  setRunStatus,
  setRunStructuredModel,
  setRunWorkingModel,
} from './state.js';

export function traceMutationContext(context) {
  const { state } = context;
  return {
    autoFollowTrace: () => state.autoFollowTrace,
    clearInlineDiagram: context.clearInlineDiagram,
    currentGenerationTraceId: () => state.currentGenerationTraceId,
    currentModelSnapshot: context.currentModelSnapshot,
    currentPlantuml: selectedPlantuml,
    currentPlantumlUrl: selectedPlantumlUrl,
    currentStructuredModel: selectedStructuredModel,
    currentWorkingModel: selectedWorkingModel,
    defaultTraceRenderLimit: context.defaultTraceRenderLimit,
    latestVisibleTraceEntry: context.latestVisibleTraceEntry,
    loadingArchivedRun: () => state.loadingArchivedRun,
    renderRunList: context.renderRunList,
    renderSequence: context.renderSequence,
    renderSessionChat: context.renderSessionChat,
    renderTraceInspector: context.renderTraceInspector,
    runtimeHarness: () => state.runtimeHarness,
    scheduleModelOutputMarkdownRender: context.scheduleModelOutputMarkdownRender,
    selectedTraceId: () => state.selectedTraceId,
    setAutoFollowTrace: (enabled) => {
      state.autoFollowTrace = Boolean(enabled);
    },
    setActiveCorrectionStreamChatId: (chatId) => {
      state.activeCorrectionStreamChatId = chatId || "";
    },
    setCurrentGenerationOutput: (runId, output) => {
      setRunOutput(runId, output);
    },
    setCurrentGenerationTraceId: (id) => {
      state.currentGenerationTraceId = id || null;
    },
    setCurrentStructuredModel: (runId, model) => {
      setRunStructuredModel(runId, model);
    },
    setCurrentPlantuml: (runId, plantuml) => {
      setRunPlantuml(runId, plantuml);
    },
    setCurrentPlantumlUrl: (runId, url) => {
      setRunPlantumlUrl(runId, url);
    },
    setCurrentWorkingModel: (runId, model) => {
      setRunWorkingModel(runId, model);
    },
    setRuntimeHarness: (harness) => {
      state.runtimeHarness = harness || null;
    },
    setSelectedRunId: (jobId) => {
      selectRun(jobId);
    },
    setSelectedRunStatus: (runId, status) => {
      setRunStatus(runId, status);
    },
    setSelectedTraceId: (traceId) => {
      state.selectedTraceId = traceId || null;
    },
    setTraceEntries: (runId, entries) => {
      setRunPresentationTrace(runId, Array.isArray(entries) ? entries : []);
    },
    setTraceRenderLimit: (limit) => {
      state.traceRenderLimit = limit;
    },
    syncBuildLogModalCurrentOutput: context.syncBuildLogModalCurrentOutput,
    traceEntries: selectedPresentationTrace,
    traceEntryVisibleForProgressFilter: context.traceEntryVisibleForProgressFilter,
    traceRenderingDeferred: context.traceRenderingDeferred,
    updateArtifactLinks: context.updateArtifactLinks,
    updateChatPanelVisibility: context.updateChatPanelVisibility,
    updateRuntimeHarnessBadge: context.updateRuntimeHarnessBadge,
    upsertTraceEntryChatBubble: context.upsertTraceEntryChatBubble,
  };
}
