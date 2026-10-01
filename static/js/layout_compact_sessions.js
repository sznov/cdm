import { els } from "./dom.js";

function setCompactSessionsOpen(open) {
  const nextOpen = Boolean(open);
  document.body.classList.toggle("compact-sessions-open", nextOpen);
  if (els.compactSessionsButton) {
    els.compactSessionsButton.setAttribute("aria-expanded", nextOpen ? "true" : "false");
    els.compactSessionsButton.title = nextOpen ? "Hide sessions" : "Show sessions";
    els.compactSessionsButton.setAttribute("aria-label", nextOpen ? "Hide sessions" : "Show sessions");
  }
}

export function compactSessionsOpen() {
  return document.body.classList.contains("compact-sessions-open");
}

export function toggleCompactSessions() {
  setCompactSessionsOpen(!compactSessionsOpen());
}

export function closeCompactSessions() {
  if (compactSessionsOpen()) setCompactSessionsOpen(false);
}
