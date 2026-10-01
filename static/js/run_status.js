export const ACTIVE_RUN_STATUSES = new Set(["queued", "running", "cancelling"]);
export const TERMINAL_RUN_STATUSES = new Set([
  "completed",
  "done",
  "failed",
  "error",
  "cancelled",
  "canceled",
  "interrupted",
]);

export function normalizeRunStatus(status) {
  return String(status || "").trim().toLowerCase();
}

export function runStatusIsActive(status) {
  return ACTIVE_RUN_STATUSES.has(normalizeRunStatus(status));
}

export function terminalStatusFromRunStatus(status) {
  const normalized = normalizeRunStatus(status);
  if (normalized === "failed" || normalized === "error") return "error";
  if (normalized === "cancelled" || normalized === "canceled" || normalized === "interrupted") {
    return "cancelled";
  }
  if (normalized === "completed" || normalized === "done") return "done";
  return "";
}

export function terminalStatusFromPhaseText(text) {
  const value = String(text || "").trim();
  if (/^(Error:|Failed\b)/i.test(value)) return "error";
  if (/^(Stopped\b|Cancelled\b|Canceled\b)/i.test(value) || /run cancelled by user/i.test(value)) {
    return "cancelled";
  }
  return "";
}

export function terminalStatusLabel(status) {
  const terminalStatus = terminalStatusFromRunStatus(status) || terminalStatusFromPhaseText(status);
  if (terminalStatus === "error") return "Failed";
  if (terminalStatus === "cancelled") return "Stopped";
  if (terminalStatus === "done") return "Done";
  return "";
}
