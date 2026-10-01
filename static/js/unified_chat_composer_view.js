import { els } from "./dom.js";
import { updateUnifiedComposerPlaceholder } from "./unified_chat_placeholder_view.js";
import { updateUnifiedSendButton } from "./unified_chat_send_button_view.js";
import { autoGrowUnifiedChatTextarea } from "./unified_chat_textarea.js";

export function updateUnifiedChatControlsView(options = {}) {
  const {
    operationPending,
    chatReady,
    hasText,
    phasesComplete,
    selectedDecisionCount,
    unresolvedDecisionCount,
  } = options;
  const hasDecisionSelection = selectedDecisionCount > 0;
  const modelChangeReady = chatReady && phasesComplete && unresolvedDecisionCount === 0 && !hasDecisionSelection && !operationPending;
  if (els.unifiedDecisionSelectionBadge) {
    els.unifiedDecisionSelectionBadge.hidden = !hasDecisionSelection;
    els.unifiedDecisionSelectionBadge.textContent =
      selectedDecisionCount === 1 ? "1 decision chosen" : `${selectedDecisionCount} decisions chosen`;
  }
  if (els.unifiedChatText) {
    els.unifiedChatText.disabled = !modelChangeReady;
    updateUnifiedComposerPlaceholder({
      chatReady,
      hasDecisionSelection,
      phasesComplete,
      selectedDecisionCount,
      unresolvedDecisionCount,
    });
    autoGrowUnifiedChatTextarea();
  }
  updateUnifiedSendButton({
    operationPending,
    chatReady,
    hasDecisionSelection,
    hasText,
    modelChangeReady,
    phasesComplete,
    unresolvedDecisionCount,
  });
}
