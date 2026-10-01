import { els } from "./dom.js";
import {
  clearDiagramControlOverflowState,
  diagramControlsShouldMountInWorkspace,
} from "./header_layout_shared.js";
import { scheduleHeaderOverflowUpdate } from "./header_overflow_menu.js";

let diagramControlsPlacementRaf = 0;
let diagramControlsPlacementTimer = 0;

function updateDiagramControlPlacement() {
  diagramControlsPlacementRaf = 0;
  if (diagramControlsPlacementTimer) {
    clearTimeout(diagramControlsPlacementTimer);
    diagramControlsPlacementTimer = 0;
  }
  if (!els.sessionDiagramControls || !els.headerOverflow) {
    clearDiagramControlOverflowState();
    scheduleHeaderOverflowUpdate();
    return;
  }
  clearDiagramControlOverflowState();
  const headerRow = els.headerOverflow.closest(".session-title-row");
  const useWorkspace = diagramControlsShouldMountInWorkspace() && Boolean(els.diagramControlMount);
  document.body.classList.toggle("diagram-controls-in-workspace", useWorkspace);
  if (useWorkspace) {
    if (els.sessionDiagramControls.parentElement !== els.diagramControlMount) {
      els.diagramControlMount.append(els.sessionDiagramControls);
    }
  } else if (headerRow && els.sessionDiagramControls.parentElement !== headerRow) {
    headerRow.insertBefore(els.sessionDiagramControls, els.headerOverflow);
  }
  scheduleHeaderOverflowUpdate();
}

export function scheduleDiagramControlPlacement() {
  if (diagramControlsPlacementRaf) return;
  diagramControlsPlacementRaf = requestAnimationFrame(updateDiagramControlPlacement);
  diagramControlsPlacementTimer = window.setTimeout(() => {
    if (!diagramControlsPlacementRaf) return;
    cancelAnimationFrame(diagramControlsPlacementRaf);
    diagramControlsPlacementRaf = 0;
    updateDiagramControlPlacement();
  }, 120);
}
