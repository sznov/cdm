import { beginAppRailResize, clampAppRailWidths, closeCompactSessions, compactSessionsOpen, resizeAppRailBy, restoreAppRailLayout, toggleAppRail, toggleCompactSessions } from './layout.js';
import { closeHeaderOverflowMenu, scheduleDiagramControlPlacement, scheduleHeaderOverflowUpdate, toggleHeaderOverflowMenu } from './header_layout.js';
import { applyTheme } from './theme.js';
import { clampDiagramWorkspaceHeight, updateDiagramCentering } from './diagram.js';
import { on } from './app_event_utils.js';

export function bindLayoutEvents(context) {
  const { elements } = context;
  let stackedLayout = window.innerWidth <= 900;

  on(elements.themeToggle, "click", () => applyTheme(document.body.classList.contains("theme-dark") ? "light" : "dark"));
  on(elements.toggleSessionRailButton, "click", () => toggleAppRail("session"));
  on(elements.compactSessionsButton, "click", (event) => {
    event.stopPropagation();
    toggleCompactSessions();
  });
  on(document, "click", (event) => {
    if (!compactSessionsOpen()) return;
    if (event.target?.closest?.(".session-rail")) return;
    closeCompactSessions();
  });
  on(document, "keydown", (event) => {
    if (event.key === "Escape") closeCompactSessions();
  });
  on(window, "resize", () => {
    if (window.innerWidth > 520) closeCompactSessions();
  });
  on(elements.toggleChatRailButton, "click", () => toggleAppRail("chat"));
  on(elements.sessionRailResizer, "pointerdown", (event) => beginAppRailResize("session", event));
  on(elements.chatRailResizer, "pointerdown", (event) => beginAppRailResize("chat", event));
  on(elements.sessionRailResizer, "keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    resizeAppRailBy("session", event.key === "ArrowLeft" ? -24 : 24);
  });
  on(elements.chatRailResizer, "keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    resizeAppRailBy("chat", event.key === "ArrowLeft" ? -24 : 24);
  });
  on(elements.headerOverflowButton, "click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    toggleHeaderOverflowMenu();
  });
  on(document, "click", (event) => {
    if (elements.headerOverflow?.contains(event.target)) return;
    closeHeaderOverflowMenu();
  });
  on(document, "keydown", (event) => {
    if (event.key === "Escape") closeHeaderOverflowMenu();
  });
  on(window, "resize", () => {
    clampDiagramWorkspaceHeight();
    const nextStackedLayout = window.innerWidth <= 900;
    if (stackedLayout && !nextStackedLayout) {
      restoreAppRailLayout();
    } else if (!nextStackedLayout) {
      clampAppRailWidths();
    }
    stackedLayout = nextStackedLayout;
    updateDiagramCentering();
    context.updateUnifiedChatControls();
    scheduleDiagramControlPlacement();
    scheduleHeaderOverflowUpdate();
  });
}

export default bindLayoutEvents;
