export function looksCorrectionLike(text) {
  const lowered = String(text || "").toLowerCase();
  return /\b(correct|fix|change|rename|remove|add|replace|normalize|repair|identifier|multiplicit|relationship|attribute|entity|patch)\b/.test(lowered);
}

export async function sendUnifiedCorrection(context, text) {
  const { elements } = context;
  if (elements.correctionText) elements.correctionText.value = text;
  context.setPendingChatCorrection("");
  if (elements.chatCorrectionConfirm) elements.chatCorrectionConfirm.hidden = true;
  await context.sendFreeformCorrection(text);
  if (elements.unifiedChatText) elements.unifiedChatText.value = "";
  context.updateUnifiedChatControls();
}

export async function sendUnifiedQuestion(context, text) {
  const { elements } = context;
  if (elements.questionText) elements.questionText.value = text;
  context.setPendingChatCorrection("");
  if (elements.chatCorrectionConfirm) elements.chatCorrectionConfirm.hidden = true;
  await context.sendQuestion();
  if (elements.unifiedChatText) elements.unifiedChatText.value = "";
  context.updateUnifiedChatControls();
}

export async function sendUnifiedChat(context) {
  const { elements } = context;
  if (context.selectedDecisionChoices().length) {
    if (elements.sendUnifiedChatButton) elements.sendUnifiedChatButton.disabled = true;
    try {
      await context.applySelectedDecisionPatches();
      if (elements.unifiedChatText) elements.unifiedChatText.value = "";
    } finally {
      context.updateUnifiedChatControls();
    }
    return;
  }
  const text = elements.unifiedChatText?.value.trim() || "";
  if (!text) return;
  if (elements.correctionsModeToggle?.checked) {
    await sendUnifiedCorrection(context, text);
    return;
  }
  if (looksCorrectionLike(text)) {
    context.setPendingChatCorrection(text);
    if (elements.chatCorrectionConfirm) elements.chatCorrectionConfirm.hidden = false;
    context.setStatus("That looks like a correction. Confirm whether to mutate the model or ask as a read-only question.");
    return;
  }
  await sendUnifiedQuestion(context, text);
}
