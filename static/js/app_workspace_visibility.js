export function updateActiveSessionWorkspaceVisibility(context) {
  const { elements } = context;
  if (!elements.activeSessionWorkspace) return;
  const hasSessionContext = Boolean(
    context.currentSession() ||
    context.selectedSessionId() ||
    context.selectedRunId()
  );
  const hasVisiblePhase = Boolean(elements.livePhasePanel && !elements.livePhasePanel.hidden);
  const hasVisibleSpec = Boolean(
    elements.frozenSpecPanel &&
      !elements.frozenSpecPanel.hidden &&
      !elements.frozenSpecPanel.classList.contains("is-hidden")
  );
  elements.activeSessionWorkspace.hidden = !(hasSessionContext && (hasVisiblePhase || hasVisibleSpec));
}

export function collapseSpecificationPanel(context) {
  const { elements } = context;
  if (elements.frozenSpecPanel) elements.frozenSpecPanel.hidden = true;
  elements.frozenSpecPanel?.classList.add("is-hidden");
  elements.frozenSpecPanel?.classList.remove("expanded");
  if (elements.showSpecButton) elements.showSpecButton.hidden = !context.currentSession();
  updateActiveSessionWorkspaceVisibility(context);
}
