import { runStatusIsActive, terminalStatusFromRunStatus } from './run_status.js';
import {
  latestPhaseStatusFromTraceEntries,
  phaseTitleFromStatus,
  terminalStatusFromPhaseText,
} from './trace_status.js';
import { updateCompactReviewRailState } from './app_review_panel_status.js';
import { updateActiveSessionWorkspaceVisibility } from './app_workspace_visibility.js';
import { runOperationPending } from './state.js';

let phasePanelActive = false;

export function activeRunPhaseStatusText(context) {
  return latestPhaseStatusFromTraceEntries(context.traceEntries()) || "Run in progress. Waiting for trace events...";
}

export function selectedRunShouldShowActivePhasePanel(context) {
  const selectedRunId = context.selectedRunId?.();
  if (!selectedRunId) return false;
  if (context.selectedRunIsActive?.()) return true;
  if (runStatusIsActive(context.selectedRunStatus?.())) return true;
  if (context.currentSession?.()?.active_job_id === selectedRunId) return true;
  return Boolean(context.traceLoadingRunId?.() === selectedRunId && runStatusIsActive(context.selectedRunStatus?.()));
}

export function updatePhasePanel(context, statusText = "") {
  const { elements } = context;
  if (!elements.livePhasePanel) return;
  const selectedRunActive = selectedRunShouldShowActivePhasePanel(context);
  const operationVisible = runOperationPending(context.selectedRunId());
  const terminalStatus =
    selectedRunActive
      ? ""
      : context.lastRunTerminalStatus() ||
        terminalStatusFromRunStatus(context.selectedRunStatus()) ||
        terminalStatusFromPhaseText(statusText);
  const terminalFeedbackVisible = Boolean(
    phasePanelActive &&
      terminalStatus &&
      terminalStatus !== "done" &&
      (context.currentSession() || context.selectedSessionId() || context.selectedRunId())
  );
  const isVisible = selectedRunActive || operationVisible || terminalFeedbackVisible;
  const isRunning = isVisible && !terminalStatus;
  let displayStatusText = statusText || "Working...";
  if (selectedRunActive && (!displayStatusText || /loaded final model/i.test(displayStatusText))) {
    displayStatusText = activeRunPhaseStatusText(context);
  }
  elements.livePhasePanel.hidden = !isVisible;
  elements.livePhasePanel.classList.toggle("is-running", isRunning);
  elements.livePhasePanel.classList.toggle("is-terminal", Boolean(isVisible && terminalStatus));
  elements.livePhasePanel.classList.toggle("is-terminal-error", terminalStatus === "error");
  elements.livePhasePanel.classList.toggle("is-terminal-cancelled", terminalStatus === "cancelled");
  if (!isVisible) {
    if (elements.phaseStatusTitle) elements.phaseStatusTitle.textContent = "";
    if (elements.phaseStatusText) elements.phaseStatusText.textContent = "";
    if (elements.rawOutput) elements.rawOutput.textContent = "";
    updateActiveSessionWorkspaceVisibility(context);
    return;
  }
  if (isVisible) {
    if (elements.phaseStatusTitle) elements.phaseStatusTitle.textContent = phaseTitleFromStatus(displayStatusText);
    if (elements.phaseStatusText) elements.phaseStatusText.textContent = displayStatusText;
  }
  updateActiveSessionWorkspaceVisibility(context);
}

export function setStatus(context, text, options = {}) {
  const statusText = text || "Idle.";
  if (context.loadingArchivedRun()) {
    context.setArchivedReplayLastStatus(statusText);
    return;
  }
  if (context.elements.status) context.elements.status.textContent = statusText;
  if (options.updatePhasePanel !== false) updatePhasePanel(context, statusText);
}

export function setRunning(context, isRunning) {
  const { elements } = context;
  const keepTerminalFeedbackVisible = Boolean(
    !isRunning &&
      context.lastRunTerminalStatus() &&
      context.lastRunTerminalStatus() !== "done" &&
      (context.currentSession() || context.selectedSessionId() || context.selectedRunId())
  );
  phasePanelActive = Boolean(isRunning) || keepTerminalFeedbackVisible;
  if (elements.runButton) {
    elements.runButton.disabled =
      isRunning ||
      !context.canRunSelectedRuntime() ||
      !context.newSessionSpecificationHasText();
  }
  if (elements.stopButton) {
    elements.stopButton.disabled = !isRunning;
    elements.stopButton.hidden = !isRunning;
  }
  updatePhasePanel(context, phasePanelActive ? elements.status?.textContent || "Working..." : "");
  updateCompactReviewRailState(context);
  context.updateRetryRunControls();
  context.renderDecisionPatches();
  context.updateCorrectionChatControls();
  context.updateQuestionChatControls();
  context.updateUnifiedChatControls();
}
