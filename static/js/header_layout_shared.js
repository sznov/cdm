import { els } from "./dom.js";

export function diagramControlElements() {
  return [
    els.sessionDiagramControls,
    els.workingModelDiagramLink,
    els.viewJsonIrButton,
    els.viewPlantumlSourceButton,
    els.diagramResetButton,
    els.diagramFitButton,
    els.diagramZoomInButton,
    els.diagramZoomOutButton,
  ].filter(Boolean);
}

export function clearDiagramControlOverflowState() {
  for (const element of diagramControlElements()) {
    element.classList.remove("is-overflowed");
  }
}

function reviewRailSeparatesHeaderFromDiagram() {
  if (!els.unifiedChatPanel || !els.diagramWorkspace) return false;
  const header = els.headerOverflow?.closest(".session-header") || document.querySelector(".session-header");
  if (!header || els.unifiedChatPanel.hidden) return false;

  const railRect = els.unifiedChatPanel.getBoundingClientRect();
  const headerRect = header.getBoundingClientRect();
  const diagramRect = els.diagramWorkspace.getBoundingClientRect();
  if (
    railRect.width < 1 ||
    railRect.height < 1 ||
    diagramRect.width < 1 ||
    diagramRect.height < 1
  ) {
    return false;
  }

  const horizontalOverlap = Math.min(railRect.right, diagramRect.right) - Math.max(railRect.left, diagramRect.left);
  const requiredOverlap = Math.min(railRect.width, diagramRect.width) * 0.5;
  return (
    railRect.top >= headerRect.bottom - 1 &&
    railRect.bottom <= diagramRect.top + 2 &&
    horizontalOverlap > requiredOverlap
  );
}

export function visibleHeaderRowOverflows(row) {
  if (!row) return false;
  const rowRect = row.getBoundingClientRect();
  if (row.scrollWidth > row.clientWidth + 1) return true;
  for (const child of [...row.children]) {
    if (child.hidden || child.classList.contains("is-overflowed")) continue;
    const style = window.getComputedStyle(child);
    if (style.display === "none" || style.visibility === "hidden") continue;
    const rect = child.getBoundingClientRect();
    if (rect.right > rowRect.right + 1 || rect.left < rowRect.left - 1) return true;
  }
  return false;
}

export function headerIdentityNeedsRoom() {
  const title = els.sessionTitle && !els.sessionTitle.hidden
    ? els.sessionTitle
    : els.sessionTitleInput && !els.sessionTitleInput.hidden
      ? els.sessionTitleInput
      : null;
  const timestamp = els.runArchiveSummary && !els.runArchiveSummary.hidden
    ? els.runArchiveSummary
    : null;
  const isClipped = (element) => {
    if (!element) return false;
    const style = window.getComputedStyle(element);
    if (style.display === "none" || style.visibility === "hidden") return false;
    return element.scrollWidth > element.clientWidth + 1;
  };
  return Boolean(isClipped(title) || isClipped(timestamp));
}

export function diagramControlsShouldMountInWorkspace() {
  const headerRow = els.headerOverflow?.closest(".session-title-row");
  if (!headerRow || !els.sessionDiagramControls) return false;
  if (els.sessionDiagramControls.parentElement !== headerRow) {
    headerRow.insertBefore(els.sessionDiagramControls, els.headerOverflow);
  }
  clearDiagramControlOverflowState();
  return (
    reviewRailSeparatesHeaderFromDiagram() ||
    visibleHeaderRowOverflows(headerRow) ||
    headerIdentityNeedsRoom()
  );
}

export function diagramControlsMountedInWorkspace() {
  return Boolean(
    els.sessionDiagramControls &&
      els.diagramControlMount &&
      els.sessionDiagramControls.parentElement === els.diagramControlMount
  );
}
