import { updateDiagramCentering } from "./diagram.js";
import {
  appRailClassName,
  defaultAppRailWidth,
  migrateStoredChatRailWidthDefault,
  persistAppRailCollapsed,
  readStoredAppRailCollapsed,
  readStoredAppRailWidth,
} from "./layout_app_rail_state.js";
import { appRailCollapsed, updateAppRailControls } from "./layout_app_rail_dom.js";
import { applyAppRailWidth } from "./layout_app_rail_width.js";

export function setAppRailCollapsed(kind, collapsed, options = {}) {
  document.body.classList.toggle(appRailClassName(kind), Boolean(collapsed));
  if (!collapsed) {
    applyAppRailWidth(kind, readStoredAppRailWidth(kind) || defaultAppRailWidth(kind), { persist: false });
  }
  if (options.persist !== false) {
    persistAppRailCollapsed(kind, collapsed);
  }
  updateAppRailControls();
  updateDiagramCentering();
}

export function toggleAppRail(kind) {
  setAppRailCollapsed(kind, !appRailCollapsed(kind));
}

export function restoreAppRailLayout() {
  const storedSessionWidth = readStoredAppRailWidth("session");
  const storedChatWidth = migrateStoredChatRailWidthDefault();
  if (storedSessionWidth) {
    applyAppRailWidth("session", storedSessionWidth, { persist: false });
  }
  if (storedChatWidth) {
    applyAppRailWidth("chat", storedChatWidth, { persist: false });
  } else {
    applyAppRailWidth("chat", defaultAppRailWidth("chat"), { persist: false });
  }
  setAppRailCollapsed("session", readStoredAppRailCollapsed("session"), {
    persist: false,
  });
  setAppRailCollapsed("chat", readStoredAppRailCollapsed("chat"), {
    persist: false,
  });
}
