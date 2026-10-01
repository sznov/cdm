import { els } from './dom.js';
import { terminalRunStatusText } from './display.js';
import { clone, formatLocalTime, shortRunId } from './format.js';
import { finalSnapshotPayloadFromTrace } from './run_session_state.js';
import { fetchHarnessTemplate } from './runtime.js';
import {
  DEFAULT_TRACE_RENDER_LIMIT,
  hydrateRunState,
  selectRun,
  selectedPlantuml,
  selectedPlantumlUrl,
  selectedPresentationTrace,
  selectedRunStatus,
  selectedStructuredModel,
  selectedWorkingModel,
  setRunOutput,
  setRunPlantuml,
  setRunPlantumlUrl,
  setRunStatus,
  setRunStructuredModel,
  setRunWorkingModel,
  state,
} from './state.js';
import { isTraceDeltaEvent } from './trace_status.js';
import { runStatusIsActive, terminalStatusFromRunStatus } from './run_status.js';
import {
  cancelRun as cancelRunWithContext,
  resumeSelectedRun as resumeSelectedRunWithContext,
  retrySelectedRun as retrySelectedRunWithContext,
  stopActiveRun as stopActiveRunWithContext,
} from './run_lifecycle_controls.js';
import { loadRun as loadRunWithContext } from './run_lifecycle_loading.js';
import {
  loadRuns as loadRunsWithContext,
  renderRunList as renderRunListWithContext,
} from './run_lifecycle_list.js';
import { clearRunOutputs as clearRunOutputsWithContext } from './run_lifecycle_status.js';

export function bindRunLifecycleController(dependencies) {
  const context = {
    activeRunPhaseStatusText: dependencies.activeRunPhaseStatusText,
    appendReplayedGenerationDelta: dependencies.appendReplayedGenerationDelta,
    applyModelSnapshotPayload: dependencies.applyModelSnapshotPayload,
    applyRunRequestToControls: dependencies.applyRunRequestToControls,
    clearInlineDiagram: dependencies.clearInlineDiagram,
    clearTrace: dependencies.clearTrace,
    elements: els,
    clone,
    currentPlantuml: selectedPlantuml,
    currentPlantumlUrl: selectedPlantumlUrl,
    currentStructuredModel: selectedStructuredModel,
    currentWorkingModel: selectedWorkingModel,
    defaultTraceRenderLimit: DEFAULT_TRACE_RENDER_LIMIT,
    fetchHarnessTemplate,
    finalSnapshotPayloadFromTrace,
    formatLocalTime,
    hydrateRunState,
    handleEvent: dependencies.handleEvent,
    isTraceDeltaEvent,
    markCurrentGenerationInterrupted: dependencies.markCurrentGenerationInterrupted,
    nextRunLoadToken: () => {
      state.runLoadToken += 1;
      return state.runLoadToken;
    },
    runLoadToken: () => state.runLoadToken,
    runRecords: () => state.runRecords,
    observeRun: dependencies.observeRun,
    perfLog: dependencies.perfLog,
    perfStart: dependencies.perfStart,
    refreshCurrentSessionRecord: dependencies.refreshCurrentSessionRecord,
    refreshModelOutputMarkdown: dependencies.refreshModelOutputMarkdown,
    renderDecisionPatches: dependencies.renderDecisionPatches,
    renderRunListView: dependencies.renderRunListView,
    renderSequence: dependencies.renderSequence,
    renderSessionChat: dependencies.renderSessionChat,
    renderTraceInspector: dependencies.renderTraceInspector,
    run: dependencies.run,
    runStatusIsActive,
    saveDiagramViewportForRun: dependencies.saveDiagramViewportForRun,
    selectedRunId: () => state.selectedRunId,
    selectedRunIsActive: dependencies.selectedRunIsActive,
    selectedRunStatus,
    selectedSessionId: () => state.selectedSessionId,
    setArchivedReplayLastStatus: (status) => {
      state.archivedReplayLastStatus = status || "";
    },
    setCurrentDecisionPatches: (patches) => {
      state.currentDecisionPatches = Array.isArray(patches) ? patches : [];
    },
    setCurrentGenerationOutput: setRunOutput,
    setCurrentPlantuml: setRunPlantuml,
    setCurrentPlantumlUrl: setRunPlantumlUrl,
    setCurrentStructuredModel: setRunStructuredModel,
    setCurrentWorkingModel: setRunWorkingModel,
    setRunning: dependencies.setRunning,
    setScrollableText: dependencies.setScrollableText,
    setStatus: dependencies.setStatus,
    setLastRunTerminalStatus: (status) => {
      state.lastRunTerminalStatus = status || null;
    },
    setLoadingArchivedRun: (loading) => {
      state.loadingArchivedRun = Boolean(loading);
    },
    setRunRecords: (runs) => {
      state.runRecords = Array.isArray(runs) ? runs : [];
    },
    setRuntimeHarness: (harness) => {
      state.runtimeHarness = harness || null;
    },
    setSelectedRunId: selectRun,
    setSelectedRunStatus: setRunStatus,
    setSelectedSessionId: (sessionId) => {
      state.selectedSessionId = sessionId || null;
    },
    setTraceLoadingRunId: (jobId) => {
      state.traceLoadingRunId = jobId || "";
    },
    setTraceRenderLimit: (limit) => {
      state.traceRenderLimit = limit;
    },
    shortRunId,
    terminalRunStatusText,
    terminalStatusFromRunStatus,
    traceEntries: selectedPresentationTrace,
    traceLoadingRunId: () => state.traceLoadingRunId,
    traceRenderLimit: () => state.traceRenderLimit,
    updateArtifactLinks: dependencies.updateArtifactLinks,
    updateChatPanelVisibility: dependencies.updateChatPanelVisibility,
    updateCorrectionChatControls: dependencies.updateCorrectionChatControls,
    updateDecisionPatches: dependencies.updateDecisionPatches,
    updateModelOutputJump: dependencies.updateModelOutputJump,
    updateQuestionChatControls: dependencies.updateQuestionChatControls,
    updateRetryRunControls: dependencies.updateRetryRunControls,
    updateRuntimeHarnessBadge: dependencies.updateRuntimeHarnessBadge,
    updateSessionHeaderSummary: dependencies.updateSessionHeaderSummary,
    updateSessionWorkspace: dependencies.updateSessionWorkspace,
    updateUnifiedChatControls: dependencies.updateUnifiedChatControls,
    yieldToBrowser: dependencies.yieldToBrowser,
  };

  function renderRunList() {
    return renderRunListWithContext(listContext);
  }
  function loadRuns() {
    return loadRunsWithContext(listContext);
  }
  function loadRun(jobId) {
    return loadRunWithContext(loadContext, jobId);
  }
  function cancelRun(jobId) {
    return cancelRunWithContext(controlContext, jobId);
  }
  function stopActiveRun() {
    return stopActiveRunWithContext(controlContext);
  }
  function retrySelectedRun() {
    return retrySelectedRunWithContext(controlContext);
  }
  function resumeSelectedRun() {
    return resumeSelectedRunWithContext(controlContext);
  }

  const listContext = { ...context, cancelRun, loadRun };
  const controlContext = { ...context, loadRuns };
  const loadContext = { ...context, renderRunList };

  return Object.freeze({
    cancelRun,
    clearRunOutputs: (options = {}) => clearRunOutputsWithContext(context, options),
    loadRun,
    loadRuns,
    renderRunList,
    resumeSelectedRun,
    retrySelectedRun,
    stopActiveRun,
  });
}
