import { els } from './dom.js';
import { openTextModal } from './text_modal.js';
import { scheduleDiagramControlPlacement, scheduleHeaderOverflowUpdate } from './header_layout.js';
import { applyRunRequestToControls, canRunSelectedRuntime, newSessionSpecificationHasText,
  updateRuntimeHarnessBadge, updateRuntimeRunControls } from './runtime.js';
import { selectedCorrectionTemplate, updateCorrectionTemplateDescription } from './correction_templates.js';
import { checkpointRetryEntry } from './run_session_state.js';
import { bindAppStatusController } from './app_status_controller.js';
import { applyModelSnapshotPayload as applyModelSnapshotPayloadFor,
  clearInlineDiagram as clearInlineDiagramFor, currentModelSnapshot as currentModelSnapshotFor,
  renderInlineDiagram as renderInlineDiagramFor, saveDiagramViewportForRun as saveDiagramViewportForRunFor,
  updateArtifactLinks as updateArtifactLinksFor,
  updateDiagramControlState as updateDiagramControlStateFor } from './model_artifact_controller.js';
import { bindModelOutputController } from './model_output_controller.js';
import { selectedRunIsActive as selectedRunIsActiveFor,
  selectedRunRecord as selectedRunRecordFor } from './run_selection_state.js';
import { appendTranscriptCheckpointCard as appendTranscriptCheckpointCardFor,
  createTranscriptCheckpointCard as createTranscriptCheckpointCardFor,
  guardedPosthocResultEntry as guardedPosthocResultEntryFor, latestVisibleTraceEntry as latestVisibleTraceEntryFor,
  workflowProgressRows as workflowProgressRowsFor, perfLog, perfStart,
  sortedTranscriptCheckpoints as sortedTranscriptCheckpointsFor, stepInputForTraceEntry as stepInputForTraceEntryFor,
  stepOutputForTraceEntry as stepOutputForTraceEntryFor,
  traceActionEntryForCheckpoint as traceActionEntryForCheckpointFor,
  traceEntryVisibleForProgressFilter as traceEntryVisibleForProgressFilterFor,
  traceRenderingDeferred as traceRenderingDeferredFor, yieldToBrowser } from './trace_derived_controller.js';
import { appendCorrectionChatMessage as appendCorrectionChatMessageFor,
  appendQuestionChatMessage as appendQuestionChatMessageFor,
  appendUnifiedChatMessage as appendUnifiedChatMessageFor, openBuildLogModal as openBuildLogModalFor,
  renderSessionChat as renderSessionChatFor,
  syncBuildLogModalCurrentOutput as syncBuildLogModalCurrentOutputFor,
  upsertCorrectionStreamChat as upsertCorrectionStreamChatFor } from './transcript_controller.js';
import { transcriptControllerContext } from './transcript_bridge_context.js';
import { addTraceEntry as addTraceEntryFor, attachCurrentStateToRecentTrace as attachCurrentStateToRecentTraceFor,
  clearTrace as clearTraceFor, updateTraceEntry as updateTraceEntryFor } from './trace_mutation_controller.js';
import { traceMutationContext } from './trace_mutation_bridge_context.js';
import { appendTraceActions as appendTraceActionsFor, applyModelToolbarIcons as applyModelToolbarIconsFor,
  canRetryFromTraceEntry as canRetryFromTraceEntryFor, jumpToCurrentTrace as jumpToCurrentTraceFor,
  renderSequence as renderSequenceFor, renderTraceInspector as renderTraceInspectorFor,
  traceRetryDisabledReason as traceRetryDisabledReasonFor,
  updateRetryRunControls as updateRetryRunControlsFor,
  updateTraceInspectorDetail as updateTraceInspectorDetailFor } from './trace_view_controller.js';
import { traceViewControllerContext } from './trace_view_bridge_context.js';
import { bindDecisionChatController } from './decision_chat_controller.js';
import { sendUnifiedChat as sendUnifiedChatFor, sendUnifiedCorrection as sendUnifiedCorrectionFor,
  sendUnifiedQuestion as sendUnifiedQuestionFor } from './unified_chat_submit_controller.js';
import { unifiedChatSubmitContext } from './unified_chat_submit_bridge_context.js';
import { markCurrentSessionRunStatus as markCurrentSessionRunStatusFor,
  sessionIsActivelyRunning as sessionIsActivelyRunningFor } from './session_workspace_state.js';
import { updateSessionHeaderSummary as updateSessionHeaderSummaryFor,
  updateSessionWorkspace as updateSessionWorkspaceFor } from './session_workspace_view.js';
import { appendReplayedGenerationDelta as appendReplayedGenerationDeltaFor, handleEvent as handleEventFor,
  handleHeadlessRunEnvelope, handleRunEnvelope as handleRunEnvelopeFor,
  markCurrentGenerationInterrupted as markCurrentGenerationInterruptedFor } from './stream_event_controller.js';
import { createRunPresentationRebuilder } from './run_presentation_replay.js';
import { createRunObservationController } from './run_observation_controller.js';
import { getRunSnapshotUrl, getRunTrace } from './runs.js';
import { run as runFor } from './run_stream_controller.js';
import { createRunStreamContext } from './run_stream_context.js';
import { bindRunLifecycleController } from './run_lifecycle_controller.js';
import { bindSessionLifecycleController } from './session_lifecycle_controller.js';
import { renderRunListView } from './session_run_view.js';
import { retryFromTraceStep as retryFromTraceStepFor } from './retry_branching.js';
import { createRetryBranchingContext } from './retry_branching_context.js';
import { applySelectedDecisionPatches as applySelectedDecisionPatchesFor,
  runCorrectionSequence as runCorrectionSequenceFor, sendFreeformCorrection as sendFreeformCorrectionFor,
  sendQuestion as sendQuestionFor } from './action_flows.js';
import { createActionFlowContext } from './action_flow_context.js';
import { startApp as startFrontendAppFor } from './app_bootstrap.js';
import { createAppBootstrapContext } from './app_bootstrap_context.js';
import { ensureRunState, hydrateRunState, selectedRunStatus, state } from './state.js';

export function createComposedAppController() {
// Cross-feature sequencing belongs here. These named workflows call leaf
// operations through fixed feature contexts; no feature owns another feature.
function appendTraceRowActions(container, entry, options = {}) { return appendTraceActionsFor(traceViewContext, container, entry, options); }
function refreshRetryControls() { return updateRetryRunControlsFor(traceViewContext); }
function renderPendingDecisions() { return decisionController.renderDecisionPatches(); }
function renderDecisionReviewRail() { return decisionController.renderDecisionRail(); }
function refreshCorrectionControls() { return decisionController.updateCorrectionChatControls(); }
function refreshDecisionOptionControls(event = null) { return decisionController.updateDecisionOptionControls(event); }
function refreshQuestionControls() { return decisionController.updateQuestionChatControls(); }
function refreshUnifiedChatControls() { return decisionController.updateUnifiedChatControls(); }
function clearSelectedRunPresentation(options = {}) { return runLifecycleController.clearRunOutputs(options); }
function refreshRunIndex() { return runLifecycleController.loadRuns(); }
function renderRunIndex() { return runLifecycleController.renderRunList(); }
function refreshSessionIndex() { return sessionLifecycleController.loadSessions(); }
function refreshSelectedSessionRecord(options = {}) { return sessionLifecycleController.refreshCurrentSessionRecord(options); }
function branchFromTraceStep(entry, retryContext = {}) { return retryFromTraceStepFor(retryBranchingContext, entry, retryContext); }
function applyPendingDecisionPatches() { return applySelectedDecisionPatchesFor(actionFlowContext); }
function submitFreeformCorrection(message = "") { return sendFreeformCorrectionFor(actionFlowContext, message); }
function submitQuestion() { return sendQuestionFor(actionFlowContext); }
function refreshSelectedModelMarkdown() { return modelOutputController.refreshModelOutputMarkdown(); }
function renderSelectedSessionTranscript() { return renderSessionChatFor(transcriptContext); }
function syncOpenBuildLogOutput(entry = null) { return syncBuildLogModalCurrentOutputFor(transcriptContext, entry); }
function ensureSelectedModelOutputBubble() { return modelOutputController.ensureModelOutputBubble(); }
function selectedModelOutputText() { return modelOutputController.modelOutputTextForDisplay(); }
function appendTranscriptCheckpointCard(checkpoint) { return appendTranscriptCheckpointCardFor(foundationContext, checkpoint); }
function createTranscriptCheckpointCard(checkpoint, viewOptions = {}) {
  return createTranscriptCheckpointCardFor(foundationContext, checkpoint, viewOptions);
}
function sortedTranscriptCheckpoints() {
  return sortedTranscriptCheckpointsFor(foundationContext);
}

const modelOutputController = bindModelOutputController({
  elements: els,
  renderSessionChat,
  syncBuildLogModalCurrentOutput,
});
const { appendText, ensureModelOutputBubble, jumpModelOutputToCurrent, modelOutputTextForDisplay,
  refreshModelOutputMarkdown, renderModelOutputMarkdown, scheduleModelOutputMarkdownRender, setModelOutputExpanded,
  setScrollableText, toggleModelOutputExpanded, updateModelOutputJump, upsertTraceEntryChatBubble } = modelOutputController;

const statusController = bindAppStatusController({
  elements: els,
  canRunSelectedRuntime,
  newSessionSpecificationHasText,
  refreshModelOutputMarkdown,
  renderDecisionPatches: renderPendingDecisions,
  selectedRunIsActive,
  updateCorrectionChatControls: refreshCorrectionControls,
  updateQuestionChatControls: refreshQuestionControls,
  updateRetryRunControls: refreshRetryControls,
  updateUnifiedChatControls: refreshUnifiedChatControls,
});
const { activeRunPhaseStatusText, collapseSpecificationPanel, currentRightRailTab, setRightRailTab,
  setRunning, setStatus, updateActiveSessionWorkspaceVisibility, updateChatPanelVisibility,
  updateCompactReviewRailState, updatePhasePanel } = statusController;

const decisionController = bindDecisionChatController({
  elements: els,
  guardedPosthocResultEntry,
  renderSessionChat,
  selectedCorrectionTemplate,
  selectedRunIsActive,
  selectedRunRecord,
  updateCompactReviewRailState,
});
const { decisionApplyPhasesComplete, renderDecisionPatches, renderDecisionRail, scrollToTranscriptDecisions,
  selectedDecisionChoices, updateApplyDecisionButtonState, updateCorrectionChatControls,
  updateDecisionOptionControls, updateDecisionPatches, updateQuestionChatControls,
  updateUnifiedChatControls } = decisionController;

const runLifecycleController = bindRunLifecycleController({
  activeRunPhaseStatusText,
  appendReplayedGenerationDelta,
  applyModelSnapshotPayload,
  applyRunRequestToControls,
  clearInlineDiagram,
  clearTrace,
  handleEvent,
  markCurrentGenerationInterrupted,
  observeRun,
  perfLog,
  perfStart,
  refreshCurrentSessionRecord: refreshSelectedSessionRecord,
  refreshModelOutputMarkdown,
  renderDecisionPatches,
  renderRunListView,
  renderSequence,
  renderSessionChat,
  renderTraceInspector,
  run,
  saveDiagramViewportForRun,
  selectedRunIsActive,
  setScrollableText,
  setRunning,
  setStatus,
  updateArtifactLinks,
  updateChatPanelVisibility,
  updateCorrectionChatControls,
  updateDecisionPatches,
  updateModelOutputJump,
  updateQuestionChatControls,
  updateRetryRunControls,
  updateRuntimeHarnessBadge,
  updateSessionHeaderSummary,
  updateSessionWorkspace,
  updateUnifiedChatControls,
  yieldToBrowser,
});
const { clearRunOutputs, loadRun, loadRuns, renderRunList, resumeSelectedRun, retrySelectedRun,
  stopActiveRun } = runLifecycleController;

const sessionLifecycleController = bindSessionLifecycleController({
  clearRunOutputs,
  clearTrace,
  loadRun,
  renderDecisionRail,
  run,
  sessionIsActivelyRunning,
  setStatus,
  updateDiagramControlState,
  updateRuntimeRunControls,
  updateSessionWorkspace,
});
const { beginSessionTitleEdit, cancelSessionTitleEdit, commitSessionTitleEdit, createSessionAndStart,
  deleteSelectedSession, loadSession, loadSessions, openDeleteSessionModal, openNewSessionModal,
  refreshCurrentSessionRecord } = sessionLifecycleController;

const foundationContext = {
  elements: els,
  state,
  appendTraceActions: appendTraceRowActions,
  appendTranscriptCheckpointCard,
  canRunSelectedRuntime,
  checkpointRetryEntry,
  createTranscriptCheckpointCard,
  currentModelSnapshot,
  ensureModelOutputBubble: ensureSelectedModelOutputBubble,
  modelOutputTextForDisplay: selectedModelOutputText,
  newSessionSpecificationHasText,
  openTextModal,
  refreshModelOutputMarkdown: refreshSelectedModelMarkdown,
  renderDecisionPatches: renderPendingDecisions,
  renderDecisionRail: renderDecisionReviewRail,
  renderSessionChat: renderSelectedSessionTranscript,
  scheduleDiagramControlPlacement,
  scheduleHeaderOverflowUpdate,
  selectedRunIsActive,
  sortedTranscriptCheckpoints,
  syncBuildLogModalCurrentOutput: syncOpenBuildLogOutput,
  updateCorrectionChatControls: refreshCorrectionControls,
  updateChatPanelVisibility,
  updateDecisionOptionControls: refreshDecisionOptionControls,
  updateQuestionChatControls: refreshQuestionControls,
  updateRetryRunControls: refreshRetryControls,
  updateUnifiedChatControls: refreshUnifiedChatControls,
};
const transcriptContext = transcriptControllerContext(foundationContext);

function appendCorrectionChatMessage(kind, text, options = {}) {
  return appendCorrectionChatMessageFor(transcriptContext, kind, text, options);
}
function appendQuestionChatMessage(kind, text, options = {}) {
  return appendQuestionChatMessageFor(transcriptContext, kind, text, options);
}
function appendUnifiedChatMessage(role, text, options = {}) {
  return appendUnifiedChatMessageFor(transcriptContext, role, text, options);
}
function applyModelSnapshotPayload(runId, payload = {}) {
  return applyModelSnapshotPayloadFor(foundationContext, runId, payload);
}
function clearInlineDiagram(message = "") { return clearInlineDiagramFor(foundationContext, message); }
function currentModelSnapshot() { return currentModelSnapshotFor(foundationContext); }
function guardedPosthocResultEntry() { return guardedPosthocResultEntryFor(foundationContext); }
function latestVisibleTraceEntry() { return latestVisibleTraceEntryFor(foundationContext); }
function openBuildLogModal() { return openBuildLogModalFor(transcriptContext); }
function workflowProgressRows() { return workflowProgressRowsFor(foundationContext); }
function renderInlineDiagram(model, options = {}) {
  return renderInlineDiagramFor(foundationContext, model, options);
}
function renderSessionChat() { return renderSessionChatFor(transcriptContext); }
function saveDiagramViewportForRun(jobId) { return saveDiagramViewportForRunFor(foundationContext, jobId); }
function liveSelectionContext() {
  return {
    currentSession: state.currentSession,
    runRecords: state.runRecords,
    selectedRunId: state.selectedRunId,
    selectedRunStatus: selectedRunStatus(),
  };
}
function selectedRunRecord() { return selectedRunRecordFor(liveSelectionContext()); }
function selectedRunIsActive() {
  const current = liveSelectionContext();
  return selectedRunIsActiveFor({ ...current, selectedRunRecord: selectedRunRecordFor(current) });
}
function stepInputForTraceEntry(entry) { return stepInputForTraceEntryFor(foundationContext, entry); }
function stepOutputForTraceEntry(entry) { return stepOutputForTraceEntryFor(foundationContext, entry); }
function syncBuildLogModalCurrentOutput(entry = null) {
  return syncBuildLogModalCurrentOutputFor(transcriptContext, entry);
}
function traceActionEntryForCheckpoint(checkpoint) {
  return traceActionEntryForCheckpointFor(foundationContext, checkpoint);
}
function traceEntryVisibleForProgressFilter(entry) {
  return traceEntryVisibleForProgressFilterFor(foundationContext, entry);
}
function traceRenderingDeferred() { return traceRenderingDeferredFor(foundationContext); }
function updateArtifactLinks() { return updateArtifactLinksFor(foundationContext); }
function updateDiagramControlState() { return updateDiagramControlStateFor(foundationContext); }
function upsertCorrectionStreamChat(text, options = {}) {
  return upsertCorrectionStreamChatFor(transcriptContext, text, options);
}

const traceContext = {
  clearInlineDiagram,
  currentModelSnapshot,
  elements: els,
  checkpointRetryEntry,
  latestVisibleTraceEntry,
  openTextModal,
  workflowProgressRows,
  renderRunList: renderRunIndex,
  renderSequence,
  renderSessionChat,
  renderTraceInspector,
  retryFromTraceStep: branchFromTraceStep,
  scheduleModelOutputMarkdownRender,
  scheduleHeaderOverflowUpdate,
  selectedRunRecord,
  setRightRailTab,
  setScrollableText,
  setStatus,
  state,
  stepInputForTraceEntry,
  stepOutputForTraceEntry,
  syncBuildLogModalCurrentOutput,
  traceActionEntryForCheckpoint,
  traceEntryVisibleForProgressFilter,
  traceRenderingDeferred,
  updateArtifactLinks,
  updateChatPanelVisibility,
  updateDiagramControlState,
  updateRuntimeHarnessBadge,
  upsertTraceEntryChatBubble,
};
const traceViewContext = traceViewControllerContext(traceContext);
const traceMutationControllerContext = traceMutationContext(traceContext);

function addTraceEntry(entry) { return addTraceEntryFor(traceMutationControllerContext, entry); }
function appendTraceActions(container, entry, options = {}) {
  return appendTraceActionsFor(traceViewContext, container, entry, options);
}
function applyModelToolbarIcons() { return applyModelToolbarIconsFor(traceViewContext); }
function attachCurrentStateToRecentTrace() {
  return attachCurrentStateToRecentTraceFor(traceMutationControllerContext);
}
function canRetryFromTraceEntry(entry) { return canRetryFromTraceEntryFor(traceViewContext, entry); }
function clearTrace(options = {}) { return clearTraceFor(traceMutationControllerContext, options); }
function jumpToCurrentTrace() { return jumpToCurrentTraceFor(traceViewContext); }
function renderSequence() { return renderSequenceFor(traceViewContext); }
function renderTraceInspector() { return renderTraceInspectorFor(traceViewContext); }
function traceRetryDisabledReason(entry) { return traceRetryDisabledReasonFor(traceViewContext, entry); }
function updateRetryRunControls() { return updateRetryRunControlsFor(traceViewContext); }
function updateTraceEntry(id, patch) { return updateTraceEntryFor(traceMutationControllerContext, id, patch); }
function updateTraceInspectorDetail(title, value) {
  return updateTraceInspectorDetailFor(traceViewContext, title, value);
}

const unifiedChatContext = unifiedChatSubmitContext({
  elements: els,
  state,
  selectedDecisionChoices,
  applySelectedDecisionPatches: applyPendingDecisionPatches,
  sendFreeformCorrection: submitFreeformCorrection,
  sendQuestion: submitQuestion,
  setStatus,
  updateUnifiedChatControls,
});

function sendUnifiedChat() { return sendUnifiedChatFor(unifiedChatContext); }
function sendUnifiedCorrection(text) { return sendUnifiedCorrectionFor(unifiedChatContext, text); }
function sendUnifiedQuestion(text) { return sendUnifiedQuestionFor(unifiedChatContext, text); }

const workspaceContext = {
  elements: els,
  state,
  renderSessionChat,
  scheduleDiagramControlPlacement,
  selectedRunIsActive,
  updateChatPanelVisibility,
  updatePhasePanel,
  updateUnifiedChatControls,
};

function markCurrentSessionRunStatus(status, jobId) {
  return markCurrentSessionRunStatusFor(workspaceContext, status, jobId);
}
function sessionIsActivelyRunning(session) { return sessionIsActivelyRunningFor(workspaceContext, session); }
function updateSessionHeaderSummary() { return updateSessionHeaderSummaryFor(workspaceContext); }
function updateSessionWorkspace() { return updateSessionWorkspaceFor(workspaceContext); }

function updateCurrentSessionRunStatus(status, jobId) {
  const changed = markCurrentSessionRunStatus(status, jobId);
  if (changed) updateSessionWorkspace();
  return changed;
}

const streamEventContext = {
  elements: els,
  state,
  addTraceEntry,
  appendCorrectionChatMessage,
  appendQuestionChatMessage,
  appendText,
  applyModelSnapshotPayload,
  attachCurrentStateToRecentTrace,
  collapseSpecificationPanel,
  loadRuns: refreshRunIndex,
  loadSessions: refreshSessionIndex,
  markCurrentSessionRunStatus: updateCurrentSessionRunStatus,
  renderDecisionRail,
  scheduleModelOutputMarkdownRender,
  setScrollableText,
  setModelOutputExpanded,
  setRightRailTab,
  setStatus,
  selectedRunIsActive,
  updateChatPanelVisibility,
  updateCorrectionChatControls,
  updateDecisionPatches,
  updateDiagramControlState,
  updateQuestionChatControls,
  updateSessionWorkspace,
  updateTraceEntry,
  updateTraceInspectorDetail,
  upsertCorrectionStreamChat,
  upsertTraceEntryChatBubble,
  clearRunOutputs: clearSelectedRunPresentation,
  clearTrace,
  setRunning,
  updateRuntimeHarnessBadge,
  updateUnifiedChatControls,
};
const rebuildPresentation = createRunPresentationRebuilder({
  state,
  getRunState: ensureRunState,
  clearRunOutputs: clearSelectedRunPresentation,
  clearTrace,
  updateRuntimeHarnessBadge,
  appendReplayedGenerationDelta: (runId, delta) => (
    appendReplayedGenerationDeltaFor(streamEventContext, runId, delta)
  ),
  handleEvent: (event, payload) => handleEventFor(streamEventContext, event, payload),
  updateSessionWorkspace,
  yieldToBrowser,
});
const runObservation = createRunObservationController({
  getRunSnapshot: (snapshotUrl) => getRunSnapshotUrl(snapshotUrl),
  getRunTracePage: (runId, options) => getRunTrace(runId, options),
  getRunState: ensureRunState,
  hydrateRunSnapshot: hydrateRunState,
  routeEnvelope: (envelope) => handleRunEnvelopeFor(streamEventContext, envelope),
  routeHistoryEnvelope: handleHeadlessRunEnvelope,
  rebuildPresentation,
  onTerminal: () => Promise.allSettled([
    refreshRunIndex(),
    refreshSessionIndex(),
  ]),
  onConnectionChange: (runId) => {
    if (state.selectedRunId === runId) updateSessionWorkspace();
  },
});
const runStreamExecutionContext = createRunStreamContext({
  clearRunOutputs: clearSelectedRunPresentation,
  clearTrace,
  handleEvent: (event, payload) => handleEventFor(streamEventContext, event, payload),
  loadRuns: refreshRunIndex,
  loadSessions: refreshSessionIndex,
  renderDecisionRail,
  observeRun: runObservation.observeRun,
  setRunning,
  setStatus,
  updateRuntimeHarnessBadge,
  updateUnifiedChatControls,
});

function appendReplayedGenerationDelta(runId, delta) {
  return appendReplayedGenerationDeltaFor(streamEventContext, runId, delta);
}
function handleEvent(event, payload) { return handleEventFor(streamEventContext, event, payload); }
function handleRunEnvelope(envelope) { return handleRunEnvelopeFor(streamEventContext, envelope); }
function markCurrentGenerationInterrupted(runId, payload = {}) {
  return markCurrentGenerationInterruptedFor(streamEventContext, runId, payload);
}
function observeRun(runId, options = {}) { return runObservation.observeRun(runId, options); }
function run(options = {}) { return runFor(runStreamExecutionContext, options); }

const retryBranchingContext = createRetryBranchingContext({
  applyRunRequestToControls,
  canRetryFromTraceEntry,
  loadSessions,
  run,
  setStatus,
  traceRetryDisabledReason,
  updateSessionWorkspace,
});
function retryFromTraceStep(entry, retryContext = {}) {
  return retryFromTraceStepFor(retryBranchingContext, entry, retryContext);
}

const actionFlowContext = createActionFlowContext({
  appendCorrectionChatMessage,
  appendQuestionChatMessage,
  appendUnifiedChatMessage,
  applyModelSnapshotPayload,
  decisionApplyPhasesComplete,
  handleRunEnvelope,
  loadRuns,
  refreshCurrentSessionRecord,
  renderDecisionPatches,
  selectedDecisionChoices,
  setStatus,
  updateApplyDecisionButtonState,
  updateCorrectionChatControls,
  updateDecisionPatches,
  updatePhasePanel,
  updateQuestionChatControls,
  updateUnifiedChatControls,
  upsertCorrectionStreamChat,
});
function applySelectedDecisionPatches() { return applySelectedDecisionPatchesFor(actionFlowContext); }
function runCorrectionSequence() { return runCorrectionSequenceFor(actionFlowContext); }
function sendFreeformCorrection(message = "") { return sendFreeformCorrectionFor(actionFlowContext, message); }
function sendQuestion() { return sendQuestionFor(actionFlowContext); }

const bootstrapContext = createAppBootstrapContext({
  applyModelToolbarIcons,
  applySelectedDecisionPatches,
  beginSessionTitleEdit,
  cancelSessionTitleEdit,
  clearTrace,
  commitSessionTitleEdit,
  createSessionAndStart,
  currentRightRailTab,
  deleteSelectedSession,
  jumpModelOutputToCurrent,
  jumpToCurrentTrace,
  loadRun,
  loadRuns,
  loadSession,
  loadSessions,
  openBuildLogModal,
  openDeleteSessionModal,
  openNewSessionModal,
  openTextModal,
  renderInlineDiagram,
  renderModelOutputMarkdown,
  saveDiagramViewportForRun,
  resumeSelectedRun,
  retrySelectedRun,
  runCorrectionSequence,
  sendFreeformCorrection,
  sendQuestion,
  sendUnifiedChat,
  sendUnifiedCorrection,
  sendUnifiedQuestion,
  setRightRailTab,
  setRunning,
  setStatus,
  statusError: (error) => setStatus(`Error: ${error.message}`),
  scrollToTranscriptDecisions,
  stopActiveRun,
  toggleModelOutputExpanded,
  updateActiveSessionWorkspaceVisibility,
  updateArtifactLinks,
  updateCorrectionChatControls,
  updateCorrectionTemplateDescription,
  updateModelOutputJump,
  updateQuestionChatControls,
  updateRetryRunControls,
  updateRuntimeHarnessBadge,
  updateSessionWorkspace,
  updateUnifiedChatControls,
});

function startAppController() {
  return startFrontendAppFor(bootstrapContext).catch((error) => setStatus(`Startup error: ${error.message}`));
}

return { startAppController };
}

export default createComposedAppController;
