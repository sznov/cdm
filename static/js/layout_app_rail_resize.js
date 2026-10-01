import {
  appRailCollapsed,
  applyAppRailWidth,
  CHAT_RAIL_DRAG_COLLAPSE_THRESHOLD,
  currentAppRailWidth,
  SESSION_RAIL_DRAG_COLLAPSE_THRESHOLD,
  setAppRailCollapsed,
} from "./layout_app_rails.js";

let appRailResizeState = null;

export function beginAppRailResize(kind, event) {
  if (event.button !== 0 || appRailCollapsed(kind)) return;
  event.preventDefault();
  appRailResizeState = {
    kind,
    startClientX: event.clientX,
    startWidth: currentAppRailWidth(kind),
  };
  document.body.classList.add("is-resizing-app-rail");
  document.addEventListener("pointermove", onAppRailResizeMove);
  document.addEventListener("pointerup", endAppRailResize);
  document.addEventListener("pointercancel", endAppRailResize);
}

function cleanupAppRailResize() {
  document.body.classList.remove("is-resizing-app-rail");
  document.removeEventListener("pointermove", onAppRailResizeMove);
  document.removeEventListener("pointerup", endAppRailResize);
  document.removeEventListener("pointercancel", endAppRailResize);
}

function onAppRailResizeMove(event) {
  if (!appRailResizeState) return;
  event.preventDefault();
  const delta = event.clientX - appRailResizeState.startClientX;
  const nextWidth =
    appRailResizeState.kind === "session"
      ? appRailResizeState.startWidth + delta
      : appRailResizeState.startWidth - delta;
  if (appRailResizeState.kind === "session" && nextWidth <= SESSION_RAIL_DRAG_COLLAPSE_THRESHOLD) {
    appRailResizeState.shouldCollapse = true;
    setAppRailCollapsed("session", true);
    appRailResizeState = null;
    cleanupAppRailResize();
    return;
  }
  if (appRailResizeState.kind === "chat" && nextWidth <= CHAT_RAIL_DRAG_COLLAPSE_THRESHOLD) {
    appRailResizeState.shouldCollapse = true;
    setAppRailCollapsed("chat", true);
    appRailResizeState = null;
    cleanupAppRailResize();
    return;
  }
  appRailResizeState.shouldCollapse = false;
  applyAppRailWidth(appRailResizeState.kind, nextWidth, { persist: false });
}

function endAppRailResize(event) {
  if (appRailResizeState) {
    const pointerNearViewportEdge =
      appRailResizeState.kind === "session" &&
      event &&
      typeof event.clientX === "number" &&
      event.clientX <= SESSION_RAIL_DRAG_COLLAPSE_THRESHOLD;
    const chatPointerNearViewportEdge =
      appRailResizeState.kind === "chat" &&
      event &&
      typeof event.clientX === "number" &&
      event.clientX >= (window.innerWidth || 0) - CHAT_RAIL_DRAG_COLLAPSE_THRESHOLD;
    if (appRailResizeState.kind === "session" && (appRailResizeState.shouldCollapse || pointerNearViewportEdge)) {
      setAppRailCollapsed("session", true);
    } else if (appRailResizeState.kind === "chat" && (appRailResizeState.shouldCollapse || chatPointerNearViewportEdge)) {
      setAppRailCollapsed("chat", true);
    } else {
      applyAppRailWidth(appRailResizeState.kind, currentAppRailWidth(appRailResizeState.kind));
    }
  }
  appRailResizeState = null;
  cleanupAppRailResize();
}
