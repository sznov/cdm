import { els } from "./dom.js";
import { appRailClassName } from "./layout_app_rail_state.js";

export function appRailCollapsed(kind) {
  return document.body.classList.contains(appRailClassName(kind));
}

export function updateAppRailControls() {
  if (els.toggleSessionRailButton) {
    const collapsed = appRailCollapsed("session");
    els.toggleSessionRailButton.title = collapsed ? "Show sessions" : "Hide sessions";
    els.toggleSessionRailButton.setAttribute("aria-label", collapsed ? "Show sessions" : "Hide sessions");
    els.toggleSessionRailButton.setAttribute("aria-expanded", collapsed ? "false" : "true");
  }
  if (els.toggleChatRailButton) {
    const collapsed = appRailCollapsed("chat");
    els.toggleChatRailButton.title = collapsed ? "Show review rail" : "Hide review rail";
    els.toggleChatRailButton.setAttribute("aria-label", collapsed ? "Show review rail" : "Hide review rail");
    els.toggleChatRailButton.setAttribute("aria-expanded", collapsed ? "false" : "true");
  }
}
