import { els } from "./dom.js";
import { useCompactUnifiedChatPlaceholder } from "./unified_chat_textarea.js";

function setUnifiedComposerPlaceholder(compactPlaceholder, fullPlaceholder, label = fullPlaceholder) {
  if (!els.unifiedChatText) return;
  els.unifiedChatText.placeholder = useCompactUnifiedChatPlaceholder() ? compactPlaceholder : fullPlaceholder;
  els.unifiedChatText.title = label;
  els.unifiedChatText.setAttribute("aria-label", label);
}

export function updateUnifiedComposerPlaceholder(options = {}) {
  const {
    chatReady,
    hasDecisionSelection,
    phasesComplete,
    selectedDecisionCount,
    unresolvedDecisionCount,
  } = options;
  if (!chatReady) {
    setUnifiedComposerPlaceholder(
      "Wait...",
      "Model actions will be available when the model is generated.",
      "Model actions will be available when the model is generated."
    );
  } else if (!phasesComplete) {
    setUnifiedComposerPlaceholder(
      "Final...",
      "Model changes will be available after the final draft.",
      "Model changes will be available after the final draft."
    );
  } else if (unresolvedDecisionCount) {
    const label =
      unresolvedDecisionCount === 1
        ? "Resolve the remaining decision before requesting changes."
        : `Resolve ${unresolvedDecisionCount} decisions before requesting changes.`;
    setUnifiedComposerPlaceholder("Decide...", label, label);
  } else if (hasDecisionSelection) {
    const label =
      selectedDecisionCount === 1
        ? "Send the selected decision before requesting changes."
        : `Send ${selectedDecisionCount} selected decisions before requesting changes.`;
    setUnifiedComposerPlaceholder("Send...", label, label);
  } else {
    setUnifiedComposerPlaceholder("Ask...", "Request a model change...", "Request a model change or ask for an explanation.");
  }
}
