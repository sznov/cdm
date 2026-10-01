import { els } from "./dom.js";

export function updateUnifiedSendButton(options = {}) {
  if (!els.sendUnifiedChatButton) return;
  const {
    operationPending,
    chatReady,
    hasDecisionSelection,
    hasText,
    modelChangeReady,
    phasesComplete,
    unresolvedDecisionCount,
  } = options;
  const canSendDecisions = chatReady && phasesComplete && hasDecisionSelection && !operationPending;
  const canSendText = modelChangeReady && hasText;
  const canSend = canSendDecisions || canSendText;
  els.sendUnifiedChatButton.disabled = !canSend;
  els.sendUnifiedChatButton.classList.toggle("is-ready", canSend);
  els.sendUnifiedChatButton.title = hasDecisionSelection
    ? phasesComplete
      ? "Send selected decisions"
      : "Decisions can be applied after all generation phases finish."
    : unresolvedDecisionCount
    ? "Resolve decisions before requesting model changes."
    : phasesComplete
    ? "Send"
    : "Model changes can be requested after the final draft.";
}
