import {
  formatJson,
  optionalClone,
} from './format.js';
import {
  clearInlineDiagramView,
  inlineDiagramObjectUrl,
  renderInlineDiagramView,
  updateArtifactLinksView,
  updateDiagramControlStateView,
} from './inline_diagram_view.js';
import { captureDiagramViewport } from './diagram.js';
import { isDarkTheme } from './theme.js';
import {
  runStateById,
  selectedPlantuml,
  selectedPlantumlUrl,
  selectedStructuredModel,
  selectedWorkingModel,
  setRunPlantuml,
  setRunPlantumlUrl,
  setRunStructuredModel,
  setRunViewport,
  setRunWorkingModel,
} from './state.js';

function diagramHasImage(elements = {}) {
  return Boolean(elements.diagramSvg?.querySelector(".diagram-svg-image"));
}

export function saveDiagramViewportForRun(context, jobId = context.state?.selectedRunId) {
  if (!jobId || !diagramHasImage(context.elements)) return null;
  const viewport = captureDiagramViewport();
  if (!viewport) return null;
  setRunViewport(jobId, viewport);
  return viewport;
}

function diagramViewportForRun(context, jobId = context.state?.selectedRunId) {
  if (!jobId) return null;
  return runStateById(jobId)?.viewport || null;
}

export function updateDiagramControlState(context) {
  const { state } = context;
  updateDiagramControlStateView({
    hasDiagram: diagramHasImage(context.elements),
    hasPlantuml: Boolean(selectedPlantuml()),
    hasModel: Boolean(selectedWorkingModel()),
    onPlacementChange: context.scheduleDiagramControlPlacement,
    onOverflowUpdate: context.scheduleHeaderOverflowUpdate,
  });
}

export function updateArtifactLinks(context) {
  updateArtifactLinksView({
    diagramUrl: inlineDiagramObjectUrl(),
    onControlStateUpdate: () => updateDiagramControlState(context),
  });
}

export function clearInlineDiagram(context, message = "") {
  clearInlineDiagramView(message, {
    onDiagramUrlChange: () => updateArtifactLinks(context),
  });
}

export function renderInlineDiagram(context, structuredModel, options = {}) {
  const selectedRunId = context.state.selectedRunId || "";
  const model = structuredModel || selectedStructuredModel();
  return renderInlineDiagramView(model, {
    ...options,
    theme: isDarkTheme() ? "dark" : "light",
    isCurrent: () => (
      (context.state.selectedRunId || "") === selectedRunId
      && selectedStructuredModel() === model
    ),
    onDiagramUrlChange: () => updateArtifactLinks(context),
    onRendered: () => updateDiagramControlState(context),
  });
}

export function currentModelSnapshot(context) {
  const { state } = context;
  return {
    working_model_snapshot: optionalClone(selectedWorkingModel()),
    structured_model_snapshot: optionalClone(selectedStructuredModel()),
    plantuml_snapshot: selectedPlantuml(),
    plantuml_url: selectedPlantumlUrl(),
  };
}

export function applyModelSnapshotPayload(context, runId, payload = {}) {
  const { elements, state } = context;
  if (payload.__replay && state.loadingArchivedRun) return true;
  const runState = runStateById(runId);
  if (!runState) return false;
  const isSelected = state.selectedRunId === runId;
  if (payload.model_snapshot) {
    setRunWorkingModel(runId, payload.model_snapshot);
    if (isSelected) {
      if (elements.workingModel) elements.workingModel.textContent = formatJson(runState.artifacts.workingModel);
      updateDiagramControlState(context);
    }
  }
  if (Object.prototype.hasOwnProperty.call(payload, "structured_model")) {
    const preserveCurrentViewport = isSelected && diagramHasImage(elements);
    const savedViewport = isSelected
      ? (preserveCurrentViewport
        ? saveDiagramViewportForRun(context, runId)
        : diagramViewportForRun(context, runId))
      : null;
    setRunStructuredModel(runId, payload.structured_model || null);
    if (isSelected) {
      renderInlineDiagram(context, runState.artifacts.structuredModel, {
        preserveViewport: preserveCurrentViewport && !savedViewport,
        viewport: savedViewport,
        version: payload.diagram_version,
      });
    }
  }
  if (payload.plantuml || payload.plantuml_url) {
    setRunPlantuml(runId, payload.plantuml || runState.artifacts.plantuml);
    setRunPlantumlUrl(runId, payload.plantuml_url || runState.artifacts.plantumlUrl);
    if (isSelected && elements.plantuml) elements.plantuml.textContent = runState.artifacts.plantuml;
  }
  if (isSelected) {
    updateArtifactLinks(context);
    context.updateChatPanelVisibility();
  }
  return true;
}
