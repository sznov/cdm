import {
  formatJson,
} from './format.js';

export function handleWorkingModelEvent(context, event, payload) {
  if (event !== "working_model") return false;
  if (payload.__replay && context.loadingArchivedRun()) return true;
  const workingModel = payload.working_model || null;
  context.setCurrentWorkingModel(workingModel);
  if (context.elements.workingModel) {
    context.elements.workingModel.textContent = workingModel ? formatJson(workingModel) : "";
  }
  context.updateDiagramControlState();
  context.updateChatPanelVisibility();
  context.attachCurrentStateToRecentTrace();
  return true;
}

export function handlePlantumlPreviewEvent(context, event, payload) {
  if (event !== "plantuml_preview") return false;
  context.applyModelSnapshotPayload(payload);
  context.attachCurrentStateToRecentTrace();
  context.addTraceEntry({
    event,
    agentId: "renderer",
    title: "PlantUML preview",
    summary: "Working model rendered to PlantUML.",
    output: payload.plantuml || "",
    payload,
  });
  return true;
}
