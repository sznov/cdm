export function unifiedChatSubmitContext(context) {
  const { state } = context;
  return {
    elements: context.elements,
    applySelectedDecisionPatches: context.applySelectedDecisionPatches,
    selectedDecisionChoices: context.selectedDecisionChoices,
    sendFreeformCorrection: context.sendFreeformCorrection,
    sendQuestion: context.sendQuestion,
    setPendingChatCorrection: (text) => {
      state.pendingChatCorrection = text || "";
    },
    setStatus: context.setStatus,
    updateUnifiedChatControls: context.updateUnifiedChatControls,
  };
}
