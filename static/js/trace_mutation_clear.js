export function clearTrace(context, options = {}) {
  const selectedRunId = context.selectedRunId?.();
  if (selectedRunId && options.clearRunState !== false) context.setTraceEntries(selectedRunId, []);
  context.setSelectedTraceId(null);
  context.setAutoFollowTrace(true);
  context.setTraceRenderLimit(context.defaultTraceRenderLimit);
  context.setCurrentGenerationTraceId(null);
  context.setActiveCorrectionStreamChatId("");
  if (selectedRunId && options.clearRunState !== false) {
    context.setCurrentGenerationOutput(selectedRunId, "");
    context.setCurrentWorkingModel(selectedRunId, null);
    context.setCurrentStructuredModel(selectedRunId, null);
    context.setCurrentPlantuml(selectedRunId, "");
    context.setCurrentPlantumlUrl(selectedRunId, "");
  }
  context.setRuntimeHarness(null);
  if (!options.keepSelectedRun) {
    context.setSelectedRunId(null);
  }
  context.updateRuntimeHarnessBadge();
  context.updateArtifactLinks();
  context.clearInlineDiagram();
  context.updateChatPanelVisibility();
  context.renderRunList();
  context.renderSequence();
  context.renderSessionChat();
  context.renderTraceInspector();
}
