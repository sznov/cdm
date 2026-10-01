import {
  selectRun,
  runStateById,
  setRunStatus,
  setRunWorkingModel,
} from './state.js';

export function runLifecycleEventContext(context, generationActions = {}, runId) {
  const { state } = context;
  const runArtifacts = () => runStateById(runId)?.artifacts;
  return {
    elements: context.elements,
    addTraceEntry: context.addTraceEntry,
    applyModelSnapshotPayload: (payload) => context.applyModelSnapshotPayload(runId, payload),
    attachCurrentStateToRecentTrace: context.attachCurrentStateToRecentTrace,
    collapseSpecificationPanel: context.collapseSpecificationPanel,
    currentDecisionPatches: () => state.currentDecisionPatches,
    currentPlantuml: () => runArtifacts()?.plantuml || "",
    currentPlantumlUrl: () => runArtifacts()?.plantumlUrl || "",
    currentStructuredModel: () => runArtifacts()?.structuredModel ?? null,
    currentSession: () => state.currentSession,
    currentWorkingModel: () => runArtifacts()?.workingModel ?? null,
    loadRuns: context.loadRuns,
    loadSessions: context.loadSessions,
    loadingArchivedRun: () => state.loadingArchivedRun,
    markCurrentGenerationInterrupted: generationActions.markCurrentGenerationInterrupted,
    markCurrentRunStatus: (status, jobId) => {
      const selectedJobId = jobId || state.selectedRunId;
      if (!selectedJobId) return;
      const selectedRun = (state.runRecords || []).find((run) => run?.job_id === selectedJobId);
      if (selectedRun) selectedRun.status = status || "";
    },
    markCurrentSessionRunStatus: context.markCurrentSessionRunStatus,
    runtimeHarness: () => state.runtimeHarness,
    selectedRunId: () => state.selectedRunId,
    setCurrentWorkingModel: (model) => {
      setRunWorkingModel(runId, model);
    },
    setLastRunTerminalStatus: (status) => {
      state.lastRunTerminalStatus = status || null;
    },
    setModelOutputExpanded: context.setModelOutputExpanded,
    setRightRailTab: context.setRightRailTab,
    setSelectedRunId: (jobId) => {
      selectRun(jobId);
    },
    setSelectedRunStatus: (status) => {
      setRunStatus(runId, status);
    },
    setSelectedSessionId: (sessionId) => {
      state.selectedSessionId = sessionId || null;
    },
    setStatus: context.setStatus,
    updateChatPanelVisibility: context.updateChatPanelVisibility,
    updateDecisionPatches: context.updateDecisionPatches,
    updateDiagramControlState: context.updateDiagramControlState,
    updateSessionWorkspace: context.updateSessionWorkspace,
  };
}
