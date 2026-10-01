import { els } from "./dom.js";

export function updateCorrectionChatControlsView(options = {}) {
  const { operationPending, hasRun, hasMessage, hasTemplate } = options;
  if (els.sendCorrectionButton) els.sendCorrectionButton.disabled = Boolean(operationPending) || !hasRun || !hasMessage;
  if (els.runCorrectionSequenceButton) {
    els.runCorrectionSequenceButton.disabled = Boolean(operationPending) || !hasRun || !hasTemplate;
  }
}

export function updateQuestionChatControlsView(options = {}) {
  const { operationPending, hasRun, hasQuestion } = options;
  if (els.sendQuestionButton) els.sendQuestionButton.disabled = Boolean(operationPending) || !hasRun || !hasQuestion;
}
