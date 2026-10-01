import {
  beginDiagramPan,
  fitDiagramToViewport,
  getDiagramZoom,
  onDiagramWheel,
  resetDiagramZoom,
  setDiagramZoom,
} from './diagram.js';
import {
  copyTextModalContent,
  downloadTextModalContent,
  handleTextModalKeydown,
} from './text_modal.js';
import { on } from './app_event_utils.js';

export function bindModelOutputEvents(context) {
  const { elements } = context;
  const saveDiagramViewportSoon = () => {
    requestAnimationFrame(() => context.saveDiagramViewportForRun?.());
  };

  on(elements.jumpToCurrent, "click", () => {
    if (elements.jumpToCurrent?.disabled) return;
    context.jumpToCurrentTrace();
  });
  on(elements.clearTrace, "click", context.clearTrace);
  on(elements.rawOutput, "scroll", context.updateModelOutputJump);
  on(elements.modelOutputJump, "click", context.jumpModelOutputToCurrent);
  on(elements.modelOutputToggle, "click", context.toggleModelOutputExpanded);

  on(elements.diagramFitButton, "click", () => {
    fitDiagramToViewport();
    saveDiagramViewportSoon();
  });
  on(elements.diagramZoomOutButton, "click", () => {
    setDiagramZoom(getDiagramZoom() - 0.15);
    saveDiagramViewportSoon();
  });
  on(elements.diagramZoomInButton, "click", () => {
    setDiagramZoom(getDiagramZoom() + 0.15);
    saveDiagramViewportSoon();
  });
  on(elements.diagramResetButton, "click", () => {
    resetDiagramZoom();
    saveDiagramViewportSoon();
  });
  on(elements.diagramSvg, "pointerdown", beginDiagramPan);
  on(elements.diagramSvg, "wheel", (event) => {
    onDiagramWheel(event);
    saveDiagramViewportSoon();
  });
  on(elements.diagramSvg, "dragstart", (event) => event.preventDefault());

  on(elements.viewPlantumlSourceButton, "click", () =>
    context.openTextModal("Current PlantUML source", context.currentPlantuml() || "(no PlantUML yet)", {
      filename: "working-model.plantuml",
      mimeType: "text/plain;charset=utf-8",
    })
  );
  on(elements.viewJsonIrButton, "click", () =>
    context.openTextModal("Current JSON IR", context.currentWorkingModel() || {}, {
      filename: "working-model.json",
      mimeType: "application/json;charset=utf-8",
    })
  );
  on(elements.copyTextModalButton, "click", () => copyTextModalContent().catch((error) => context.setStatus(`Copy failed: ${error.message}`)));
  on(elements.downloadTextModalButton, "click", downloadTextModalContent);
  on(elements.textModal, "keydown", handleTextModalKeydown);
  on(elements.closeTextModalButton, "click", () => elements.textModal?.close());
  on(elements.closeBuildLogModalButton, "click", () => elements.buildLogModal?.close());
}

export default bindModelOutputEvents;
