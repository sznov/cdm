import { els } from "./dom.js";
import {
  clearDiagramControlOverflowState,
  diagramControlsMountedInWorkspace,
  diagramControlsShouldMountInWorkspace,
  headerIdentityNeedsRoom,
  visibleHeaderRowOverflows,
} from "./header_layout_shared.js";
import {
  headerOverflowCandidates,
  isHeaderOverflowCandidateActive,
} from "./header_overflow_candidates.js";
import {
  closeHeaderOverflowMenu,
  isHeaderActionDisabled,
  renderHeaderOverflowMenu,
  toggleHeaderOverflowMenu,
} from "./header_overflow_menu_view.js";

let headerOverflowRaf = 0;
let headerOverflowFallbackTimer = 0;

function activateHeaderOverflowAction(element) {
  if (!element || isHeaderActionDisabled(element)) return;
  closeHeaderOverflowMenu();
  if (element instanceof HTMLAnchorElement) {
    window.open(element.href, "_blank", "noreferrer");
    return;
  }
  element.click();
}

function updateHeaderOverflowState() {
  headerOverflowRaf = 0;
  if (headerOverflowFallbackTimer) {
    clearTimeout(headerOverflowFallbackTimer);
    headerOverflowFallbackTimer = 0;
  }
  if (!els.headerOverflow || !els.headerOverflowButton || !els.headerOverflowMenu) return;
  const row = els.headerOverflow.closest(".session-title-row");
  if (!row) return;
  clearDiagramControlOverflowState();
  if (!diagramControlsMountedInWorkspace() && diagramControlsShouldMountInWorkspace() && els.diagramControlMount) {
    document.body.classList.add("diagram-controls-in-workspace");
    if (els.sessionDiagramControls?.parentElement !== els.diagramControlMount) {
      els.diagramControlMount.append(els.sessionDiagramControls);
    }
    els.headerOverflow.hidden = true;
    els.headerOverflowButton.disabled = true;
    closeHeaderOverflowMenu();
    scheduleHeaderOverflowUpdate();
    return;
  }
  const wasOpen = !els.headerOverflowMenu.hidden;
  const candidates = headerOverflowCandidates().filter(isHeaderOverflowCandidateActive);
  for (const candidate of candidates) {
    candidate.element.classList.remove("is-overflowed");
  }
  els.headerOverflow.hidden = true;
  els.headerOverflowButton.disabled = true;
  if (!candidates.length) {
    closeHeaderOverflowMenu();
    return;
  }
  const hiddenCandidates = [];
  const ensureMenuMeasured = () => {
    els.headerOverflow.hidden = false;
    els.headerOverflowButton.disabled = false;
  };
  const headerNeedsOverflow = () => visibleHeaderRowOverflows(row) || headerIdentityNeedsRoom();
  if (headerNeedsOverflow()) {
    ensureMenuMeasured();
  }
  for (const candidate of candidates) {
    if (!headerNeedsOverflow()) break;
    candidate.element.classList.add("is-overflowed");
    if (candidate.menuCandidates?.length) {
      for (const menuCandidate of candidate.menuCandidates) {
        if (!hiddenCandidates.includes(menuCandidate)) hiddenCandidates.push(menuCandidate);
      }
    } else {
      hiddenCandidates.push(candidate);
    }
    ensureMenuMeasured();
  }
  if (!hiddenCandidates.length) {
    els.headerOverflow.hidden = true;
    els.headerOverflowButton.disabled = true;
    closeHeaderOverflowMenu();
    return;
  }
  renderHeaderOverflowMenu(hiddenCandidates, activateHeaderOverflowAction);
  if (wasOpen) {
    els.headerOverflowMenu.hidden = false;
    els.headerOverflowButton.setAttribute("aria-expanded", "true");
  } else {
    closeHeaderOverflowMenu();
  }
}

export function scheduleHeaderOverflowUpdate() {
  if (headerOverflowRaf) return;
  headerOverflowRaf = requestAnimationFrame(updateHeaderOverflowState);
  headerOverflowFallbackTimer = window.setTimeout(() => {
    if (!headerOverflowRaf) return;
    cancelAnimationFrame(headerOverflowRaf);
    headerOverflowRaf = 0;
    updateHeaderOverflowState();
  }, 120);
}

export { closeHeaderOverflowMenu, toggleHeaderOverflowMenu };
