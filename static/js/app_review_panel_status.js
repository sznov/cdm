import { runOperationPending } from './state.js';

export function updateChatPanelVisibility(context) {
  const { elements } = context;
  if (!elements.unifiedChatPanel) return;
  const hasSession = Boolean(
    context.currentSession() ||
    context.selectedSessionId() ||
    context.selectedRunId()
  );
  const chatReady = Boolean(context.currentWorkingModel() && context.selectedRunId());
  elements.unifiedChatPanel.hidden = !hasSession;
  elements.unifiedChatPanel.classList.toggle("is-chat-ready", chatReady);
  if (elements.chatAvailabilityNote) {
    elements.chatAvailabilityNote.textContent = chatReady
      ? "Request a model change or ask for an explanation."
      : "Model actions will be available when the model is generated.";
  }
  context.updateUnifiedChatControls();
  context.refreshModelOutputMarkdown();
  updateCompactReviewRailState(context);
}

export function reviewRailHasUsefulCompactContent(context) {
  const hasPatches = Array.isArray(context.currentDecisionPatches()) && context.currentDecisionPatches().length > 0;
  const hasModel = Boolean(context.currentWorkingModel());
  const hasVisibleLivePhase = Boolean(context.elements.livePhasePanel && !context.elements.livePhasePanel.hidden);
  const activeRunVisible = runOperationPending(context.selectedRunId()) || context.selectedRunIsActive();
  return hasPatches || hasModel || hasVisibleLivePhase || activeRunVisible;
}

export function updateCompactReviewRailState(context) {
  const hasSession = Boolean(
    context.currentSession() ||
    context.selectedSessionId() ||
    context.selectedRunId()
  );
  document.body.classList.toggle(
    "compact-review-rail-passive",
    hasSession && !reviewRailHasUsefulCompactContent(context)
  );
}
