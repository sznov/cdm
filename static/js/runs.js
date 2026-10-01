import { fetchJson } from "./api.js";

export function listRuns() {
  return fetchJson("/api/runs", { cache: "no-store" });
}

export function createRun(payload) {
  return fetchJson("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
}

export function getRun(jobId, options = {}) {
  const hasIncludeTrace = Object.prototype.hasOwnProperty.call(options, "includeTrace");
  const query = hasIncludeTrace ? `?include_trace=${options.includeTrace ? "true" : "false"}` : "";
  return fetchJson(`/api/runs/${encodeURIComponent(jobId)}${query}`, options.cache ? { cache: options.cache } : {});
}

export function getRunSnapshotUrl(url) {
  return fetchJson(url, { cache: "no-store" });
}

export function getRunTrace(jobId, options = {}) {
  const query = new URLSearchParams();
  if (typeof options.cursor === "string" && options.cursor) {
    query.set("cursor", options.cursor);
  } else if (Number.isInteger(options.after) && options.after >= 0) {
    query.set("after", String(options.after));
  }
  if (Number.isInteger(options.limit) && options.limit > 0) query.set("limit", String(options.limit));
  const suffix = query.size ? `?${query}` : "";
  return fetchJson(`/api/runs/${encodeURIComponent(jobId)}/trace${suffix}`, { cache: "no-store" });
}

export function cancelRunRequest(jobId) {
  return fetchJson(`/api/runs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
}

export function applyDecisionPatchChoices(jobId, decisions) {
  return fetchJson(`/api/runs/${encodeURIComponent(jobId)}/decision-patches/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decisions }),
  });
}
