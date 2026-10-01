import { els } from "./dom.js";

export function updateDiagramControlStateView(options = {}) {
  const { hasDiagram, hasPlantuml, hasModel, onPlacementChange, onOverflowUpdate } = options;
  for (const button of [els.diagramFitButton, els.diagramZoomOutButton, els.diagramZoomInButton, els.diagramResetButton]) {
    if (button) button.disabled = !hasDiagram;
  }
  if (els.viewPlantumlSourceButton) els.viewPlantumlSourceButton.disabled = !hasPlantuml;
  if (els.viewJsonIrButton) els.viewJsonIrButton.disabled = !hasModel;
  if (typeof onPlacementChange === "function") onPlacementChange();
  if (typeof onOverflowUpdate === "function") onOverflowUpdate();
}
