import { runStatusIsActive } from "./run_status.js";

export function selectedRunRecord(context = {}) {
  return (context.runRecords || []).find((run) => run.job_id === context.selectedRunId) || null;
}

export function selectedRunIsActive(context = {}) {
  const selected = context.selectedRunRecord || selectedRunRecord(context);
  return Boolean(
    runStatusIsActive(context.selectedRunStatus) ||
      runStatusIsActive(selected?.status) ||
      (context.selectedRunId && context.currentSession?.active_job_id === context.selectedRunId)
  );
}
