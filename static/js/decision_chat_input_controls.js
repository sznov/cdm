import {
  updateCorrectionChatControlsView,
  updateQuestionChatControlsView,
  updateUnifiedChatControlsView,
} from './unified_chat_view.js';
import {
  decisionApplyPhasesComplete,
  pendingDecisionPatchCount,
  selectedDecisionChoices,
} from './decision_chat_state.js';
import { runActionBlocked } from './state.js';

export function updateCorrectionChatControls(context) {
  const hasRun = Boolean(context.selectedRunId());
  const hasMessage = Boolean(context.elements.correctionText?.value.trim());
  const selectedTemplate = context.selectedCorrectionTemplate();
  const hasTemplate = Boolean(selectedTemplate && (selectedTemplate.steps || []).length);
  updateCorrectionChatControlsView({
    operationPending: runActionBlocked(context.selectedRunId()),
    hasRun,
    hasMessage,
    hasTemplate,
  });
}

export function updateQuestionChatControls(context) {
  const hasRun = Boolean(context.selectedRunId());
  const hasQuestion = Boolean(context.elements.questionText?.value.trim());
  updateQuestionChatControlsView({
    operationPending: runActionBlocked(context.selectedRunId()),
    hasRun,
    hasQuestion,
  });
}

export function updateUnifiedChatControls(context) {
  const hasRun = Boolean(context.selectedRunId());
  const chatReady = Boolean(context.currentWorkingModel() && hasRun);
  const hasText = Boolean(context.elements.unifiedChatText?.value.trim());
  const selectedDecisionCount = selectedDecisionChoices(context).length;
  const phasesComplete = decisionApplyPhasesComplete(context);
  const unresolvedDecisionCount = pendingDecisionPatchCount(context);
  updateUnifiedChatControlsView({
    operationPending: runActionBlocked(context.selectedRunId()),
    chatReady,
    hasText,
    phasesComplete,
    selectedDecisionCount,
    unresolvedDecisionCount,
  });
}
