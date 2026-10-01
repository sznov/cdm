const SESSION_RAIL_WIDTH_STORAGE_KEY = "cdmapp.sessionRailWidth";
const CHAT_RAIL_WIDTH_STORAGE_KEY = "cdmapp.chatRailWidth";
const CHAT_RAIL_DEFAULT_VERSION_STORAGE_KEY = "cdmapp.chatRailDefaultVersion";
const SESSION_RAIL_COLLAPSED_STORAGE_KEY = "cdmapp.sessionRailCollapsed";
const CHAT_RAIL_COLLAPSED_STORAGE_KEY = "cdmapp.chatRailCollapsed";
const CHAT_RAIL_DEFAULT_VERSION = "wide-300";

export const DEFAULT_SESSION_RAIL_WIDTH = 220;
export const DEFAULT_CHAT_RAIL_WIDTH = 300;
export const SESSION_RAIL_DRAG_COLLAPSE_THRESHOLD = 72;
export const CHAT_RAIL_DRAG_COLLAPSE_THRESHOLD = 72;

export function appRailClassName(kind) {
  return kind === "session" ? "session-rail-collapsed" : "chat-rail-collapsed";
}

export function appRailWidthPropertyName(kind) {
  return kind === "session" ? "--session-rail-width" : "--chat-rail-width";
}

export function appRailWidthStorageKey(kind) {
  return kind === "session" ? SESSION_RAIL_WIDTH_STORAGE_KEY : CHAT_RAIL_WIDTH_STORAGE_KEY;
}

export function appRailCollapsedStorageKey(kind) {
  return kind === "session" ? SESSION_RAIL_COLLAPSED_STORAGE_KEY : CHAT_RAIL_COLLAPSED_STORAGE_KEY;
}

export function defaultAppRailWidth(kind) {
  return kind === "session" ? DEFAULT_SESSION_RAIL_WIDTH : DEFAULT_CHAT_RAIL_WIDTH;
}

export function readStoredAppRailWidth(kind) {
  const storedWidth = Number(localStorage.getItem(appRailWidthStorageKey(kind)));
  return Number.isFinite(storedWidth) && storedWidth > 0 ? storedWidth : null;
}

export function persistAppRailWidth(kind, width) {
  localStorage.setItem(appRailWidthStorageKey(kind), String(width));
}

export function readStoredAppRailCollapsed(kind) {
  return localStorage.getItem(appRailCollapsedStorageKey(kind)) === "1";
}

export function persistAppRailCollapsed(kind, collapsed) {
  localStorage.setItem(appRailCollapsedStorageKey(kind), collapsed ? "1" : "0");
}

export function migrateStoredChatRailWidthDefault() {
  let storedChatWidth = Number(localStorage.getItem(CHAT_RAIL_WIDTH_STORAGE_KEY));
  const chatDefaultVersion = localStorage.getItem(CHAT_RAIL_DEFAULT_VERSION_STORAGE_KEY);
  if (
    chatDefaultVersion !== CHAT_RAIL_DEFAULT_VERSION &&
    (!Number.isFinite(storedChatWidth) || storedChatWidth <= DEFAULT_SESSION_RAIL_WIDTH)
  ) {
    storedChatWidth = DEFAULT_CHAT_RAIL_WIDTH;
    localStorage.setItem(CHAT_RAIL_WIDTH_STORAGE_KEY, String(DEFAULT_CHAT_RAIL_WIDTH));
    localStorage.setItem(CHAT_RAIL_DEFAULT_VERSION_STORAGE_KEY, CHAT_RAIL_DEFAULT_VERSION);
  }
  return Number.isFinite(storedChatWidth) && storedChatWidth > 0 ? storedChatWidth : null;
}
