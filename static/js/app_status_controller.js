import {
  activeRunPhaseStatusText,
  setRunning,
  setStatus,
  updatePhasePanel,
} from './app_phase_status.js';
import {
  updateChatPanelVisibility,
  updateCompactReviewRailState,
} from './app_review_panel_status.js';
import {
  currentRightRailTab,
  setRightRailTab,
} from './app_right_rail_tabs.js';
import {
  collapseSpecificationPanel,
  updateActiveSessionWorkspaceVisibility,
} from './app_workspace_visibility.js';
import {
  selectedPresentationTrace,
  selectedRunStatus,
  selectedWorkingModel,
  state,
} from './state.js';

export function bindAppStatusController(dependencies) {
  const context = {
    elements: dependencies.elements,
    canRunSelectedRuntime: dependencies.canRunSelectedRuntime,
    currentDecisionPatches: () => state.currentDecisionPatches,
    currentSession: () => state.currentSession,
    currentWorkingModel: selectedWorkingModel,
    lastRunTerminalStatus: () => state.lastRunTerminalStatus,
    loadingArchivedRun: () => state.loadingArchivedRun,
    newSessionSpecificationHasText: dependencies.newSessionSpecificationHasText,
    refreshModelOutputMarkdown: dependencies.refreshModelOutputMarkdown,
    renderDecisionPatches: dependencies.renderDecisionPatches,
    selectedRunId: () => state.selectedRunId,
    selectedRunIsActive: dependencies.selectedRunIsActive,
    selectedRunStatus,
    selectedSessionId: () => state.selectedSessionId,
    setArchivedReplayLastStatus: (status) => {
      state.archivedReplayLastStatus = status || "";
    },
    traceEntries: selectedPresentationTrace,
    traceLoadingRunId: () => state.traceLoadingRunId,
    updateCorrectionChatControls: dependencies.updateCorrectionChatControls,
    updateQuestionChatControls: dependencies.updateQuestionChatControls,
    updateRetryRunControls: dependencies.updateRetryRunControls,
    updateUnifiedChatControls: dependencies.updateUnifiedChatControls,
  };
  return Object.freeze({
    activeRunPhaseStatusText: () => activeRunPhaseStatusText(context),
    collapseSpecificationPanel: () => collapseSpecificationPanel(context),
    currentRightRailTab,
    setRightRailTab: (tabId) => setRightRailTab(context, tabId),
    setRunning: (isRunning) => setRunning(context, isRunning),
    setStatus: (text, options = {}) => setStatus(context, text, options),
    updateActiveSessionWorkspaceVisibility: () => updateActiveSessionWorkspaceVisibility(context),
    updateChatPanelVisibility: () => updateChatPanelVisibility(context),
    updateCompactReviewRailState: () => updateCompactReviewRailState(context),
    updatePhasePanel: (statusText = "") => updatePhasePanel(context, statusText),
  });
}
