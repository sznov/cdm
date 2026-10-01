import { selectedPresentationTrace } from './state.js';

export function transcriptControllerContext(context) {
  const { state } = context;
  return {
    elements: context.elements,
    activeCorrectionStreamChatId: () => state.activeCorrectionStreamChatId,
    appendTranscriptCheckpointCard: context.appendTranscriptCheckpointCard,
    createTranscriptCheckpointCard: context.createTranscriptCheckpointCard,
    currentGenerationTraceId: () => state.currentGenerationTraceId,
    currentSession: () => state.currentSession,
    ensureModelOutputBubble: context.ensureModelOutputBubble,
    modelOutputTextForDisplay: context.modelOutputTextForDisplay,
    openTextModal: context.openTextModal,
    refreshModelOutputMarkdown: context.refreshModelOutputMarkdown,
    renderDecisionRail: context.renderDecisionRail,
    renderingSessionTranscript: () => state.renderingSessionTranscript,
    setActiveCorrectionStreamChatId: (chatId) => {
      state.activeCorrectionStreamChatId = chatId || "";
    },
    setRenderingSessionTranscript: (rendering) => {
      state.renderingSessionTranscript = Boolean(rendering);
    },
    sortedTranscriptCheckpoints: context.sortedTranscriptCheckpoints,
    traceEntries: selectedPresentationTrace,
    updateDecisionOptionControls: context.updateDecisionOptionControls,
  };
}
