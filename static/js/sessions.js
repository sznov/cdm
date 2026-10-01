import { fetchJson } from "./api.js";

export function listSessions() {
  return fetchJson("/api/sessions");
}

export function getSession(sessionId) {
  return fetchJson(`/api/sessions/${encodeURIComponent(sessionId)}`);
}

export function createSession(payload) {
  return fetchJson("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updateSession(sessionId, payload) {
  return fetchJson(`/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function removeSession(sessionId) {
  return fetchJson(`/api/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
}
