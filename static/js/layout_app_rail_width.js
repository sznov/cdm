import { els } from "./dom.js";
import { updateDiagramCentering } from "./diagram.js";
import { appRailWidthBounds } from "./layout_app_rail_measure.js";
import {
  appRailWidthPropertyName,
  defaultAppRailWidth,
  persistAppRailWidth,
} from "./layout_app_rail_state.js";
import {
  notifyChatRailWidthChanged,
  sessionRecordsForRail,
} from "./layout_app_rail_config.js";
import { appRailCollapsed } from "./layout_app_rail_dom.js";

let sessionRailWidthClampFrame = 0;

export function scheduleSessionRailWidthClamp() {
  if (sessionRailWidthClampFrame) return;
  sessionRailWidthClampFrame = window.requestAnimationFrame(() => {
    sessionRailWidthClampFrame = 0;
    if (!appRailCollapsed("session")) {
      applyAppRailWidth("session", currentAppRailWidth("session"), { persist: false });
    }
  });
}

export function currentAppRailWidth(kind) {
  const element = kind === "session" ? document.querySelector(".session-rail") : els.unifiedChatPanel;
  return element?.getBoundingClientRect().width || defaultAppRailWidth(kind);
}

export function applyAppRailWidth(kind, width, options = {}) {
  const numeric = Number(width);
  if (!Number.isFinite(numeric) || numeric <= 0) return;
  const { minWidth, maxWidth } = appRailWidthBounds(kind, {
    sessionList: els.sessionList,
    sessionRecords: sessionRecordsForRail(),
  });
  const clamped = Math.max(minWidth, Math.min(maxWidth, Math.round(numeric)));
  const propertyName = appRailWidthPropertyName(kind);
  document.documentElement.style.setProperty(propertyName, `${clamped}px`);
  if (options.persist !== false) {
    persistAppRailWidth(kind, clamped);
  }
  if (kind === "chat") notifyChatRailWidthChanged();
  updateDiagramCentering();
}

export function clampAppRailWidths() {
  if (!appRailCollapsed("session")) {
    applyAppRailWidth("session", currentAppRailWidth("session"), { persist: false });
  }
  if (!appRailCollapsed("chat")) {
    applyAppRailWidth("chat", currentAppRailWidth("chat"), { persist: false });
  }
}

export function resizeAppRailBy(kind, delta) {
  if (appRailCollapsed(kind)) return;
  const direction = kind === "session" ? 1 : -1;
  applyAppRailWidth(kind, currentAppRailWidth(kind) + delta * direction);
}
