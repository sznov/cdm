import {
  formatCompactLocalTime,
  formatLocalTime,
  shortRunId,
} from "./format.js";
import {
  runStatusIsActive,
  terminalStatusFromRunStatus,
} from "./run_status.js";

export { runStatusIsActive, terminalStatusFromRunStatus };

export function sessionCustomTitle(session) {
  const title = String(session?.title || "").trim();
  return session?.title_source === "user" && title ? title : "";
}

export function sessionDisplayDate(session, selectedRun = null) {
  return formatCompactLocalTime(selectedRun?.started_at_utc || session?.created_at_utc || session?.updated_at_utc);
}

export function sessionDisplayTitle(session, selectedRun = null) {
  return sessionCustomTitle(session) || sessionDisplayDate(session, selectedRun);
}

export function sessionDisplaySubtitle(session, selectedRun = null) {
  return sessionCustomTitle(session) ? sessionDisplayDate(session, selectedRun) : "";
}

export function sessionTitleDefaultText(session, selectedRun = null) {
  return sessionDisplayDate(session, selectedRun);
}

export function terminalRunStatusText(run = {}, summary = {}, context = {}) {
  const status = terminalStatusFromRunStatus(run.status || summary.status || context.selectedRunStatus);
  if (!status) return "";
  const jobId = run.job_id || summary.job_id || context.selectedRunId;
  const label = jobId ? shortRunId(jobId) : "run";
  if (status === "error") {
    return `Failed ${label}: ${run.error || summary.error || "Run failed."}`;
  }
  if (status === "cancelled") {
    return `Stopped ${label}: ${run.error || summary.error || "Run cancelled."}`;
  }
  const startedAt = run.started_at_utc || summary.started_at_utc;
  return startedAt ? `Loaded final model from ${formatLocalTime(startedAt)}.` : "Loaded final model.";
}
