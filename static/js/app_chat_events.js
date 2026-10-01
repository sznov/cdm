import { on } from './app_event_utils.js';

export function bindChatEvents(context) {
  const { elements } = context;

  on(elements.correctionText, "input", context.updateCorrectionChatControls);
  on(elements.questionText, "input", context.updateQuestionChatControls);
  on(elements.correctionTemplateSelect, "change", () => {
    context.updateCorrectionTemplateDescription();
    context.updateCorrectionChatControls();
  });
  on(elements.runCorrectionSequenceButton, "click", () =>
    context.runCorrectionSequence().catch((error) => {
      context.statusError(error);
      context.updateCorrectionChatControls();
    })
  );
  on(elements.sendCorrectionButton, "click", () =>
    context.sendFreeformCorrection().catch((error) => {
      context.statusError(error);
      context.updateCorrectionChatControls();
    })
  );
  on(elements.sendQuestionButton, "click", () =>
    context.sendQuestion().catch((error) => {
      context.statusError(error);
      context.updateQuestionChatControls();
    })
  );
  on(elements.livePhasePanel, "click", () => context.openBuildLogModal({ scrollToBottom: true }));
  on(elements.livePhasePanel, "keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      context.openBuildLogModal({ scrollToBottom: true });
    }
  });
  on(elements.sessionDecisionNotice, "click", context.scrollToTranscriptDecisions);
  on(elements.viewBuildLogButton, "click", context.openBuildLogModal);
  for (const tabButton of elements.rightRailTabs || []) {
    tabButton.addEventListener("click", () => context.setRightRailTab(tabButton.dataset.railTab || "progress"));
  }
  context.setRightRailTab(context.currentRightRailTab());

  on(elements.unifiedChatText, "input", context.updateUnifiedChatControls);
  on(elements.unifiedChatText, "keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      context.sendUnifiedChat().catch(context.statusError);
    }
  });
  on(elements.sendUnifiedChatButton, "click", () => context.sendUnifiedChat().catch(context.statusError));
  on(elements.confirmCorrectionButton, "click", () =>
    context.sendUnifiedCorrection(context.pendingChatCorrection()).catch(context.statusError)
  );
  on(elements.askInsteadButton, "click", () =>
    context.sendUnifiedQuestion(context.pendingChatCorrection()).catch(context.statusError)
  );

  on(elements.viewSpecButton, "click", () => elements.frozenSpecPanel?.classList.toggle("expanded"));
  on(elements.hideSpecButton, "click", () => {
    if (elements.frozenSpecPanel) elements.frozenSpecPanel.hidden = true;
    elements.frozenSpecPanel?.classList.add("is-hidden");
    if (elements.showSpecButton) elements.showSpecButton.hidden = false;
    context.updateActiveSessionWorkspaceVisibility();
  });
  on(elements.showSpecButton, "click", () => {
    if (elements.frozenSpecPanel) elements.frozenSpecPanel.hidden = false;
    elements.frozenSpecPanel?.classList.remove("is-hidden");
    if (elements.showSpecButton) elements.showSpecButton.hidden = true;
    context.updateActiveSessionWorkspaceVisibility();
  });
}

export default bindChatEvents;
