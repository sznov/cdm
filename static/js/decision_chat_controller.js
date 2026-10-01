import {
  decisionApplyPhasesComplete,
  renderDecisionPatches,
  renderDecisionRail,
  scrollToTranscriptDecisions,
  selectedDecisionChoices,
  updateApplyDecisionButtonState,
  updateCorrectionChatControls,
  updateDecisionOptionControls,
  updateDecisionPatches,
  updateQuestionChatControls,
  updateUnifiedChatControls,
} from './decision_chat_controls.js';
import {
  selectedRunStatus,
  selectedWorkingModel,
  state,
} from './state.js';

export function bindDecisionChatController(dependencies) {
  const context = {
    elements: dependencies.elements,
    currentDecisionPatches: () => state.currentDecisionPatches,
    currentSession: () => state.currentSession,
    currentWorkingModel: selectedWorkingModel,
    guardedPosthocResultEntry: dependencies.guardedPosthocResultEntry,
    renderingSessionTranscript: () => state.renderingSessionTranscript,
    renderSessionChat: dependencies.renderSessionChat,
    selectedCorrectionTemplate: dependencies.selectedCorrectionTemplate,
    selectedRunId: () => state.selectedRunId,
    selectedRunIsActive: dependencies.selectedRunIsActive,
    selectedRunRecord: dependencies.selectedRunRecord,
    selectedRunStatus,
    setCurrentDecisionPatches: (patches) => {
      state.currentDecisionPatches = Array.isArray(patches) ? patches : [];
    },
    updateCompactReviewRailState: dependencies.updateCompactReviewRailState,
  };
  return Object.freeze({
    decisionApplyPhasesComplete: () => decisionApplyPhasesComplete(context),
    renderDecisionPatches: () => renderDecisionPatches(context),
    renderDecisionRail: () => renderDecisionRail(context),
    scrollToTranscriptDecisions: () => scrollToTranscriptDecisions(context),
    selectedDecisionChoices: () => selectedDecisionChoices(context),
    updateApplyDecisionButtonState: () => updateApplyDecisionButtonState(context),
    updateCorrectionChatControls: () => updateCorrectionChatControls(context),
    updateDecisionOptionControls: (event = null) => updateDecisionOptionControls(context, event),
    updateDecisionPatches: (patches = []) => updateDecisionPatches(context, patches),
    updateQuestionChatControls: () => updateQuestionChatControls(context),
    updateUnifiedChatControls: () => updateUnifiedChatControls(context),
  });
}
