import { runStatusIsActive } from "./run_status.js";

export function sessionLatestJobId(session = null) {
  if (!session) return "";
  const jobs = Array.isArray(session.job_ids) ? session.job_ids : [];
  return session.active_job_id || jobs[jobs.length - 1] || session.latest_job_id || "";
}

export function sessionOwnsJob(session, jobId) {
  if (!session || !jobId) return false;
  return session.active_job_id === jobId || (session.job_ids || []).includes(jobId) || session.latest_job_id === jobId;
}

export function sessionIsActivelyRunning(session, context = {}) {
  return Boolean(
    session &&
      (
        runStatusIsActive(session.status) ||
        session.active_job_id
      )
  );
}

export function activeSessionIdForCurrentRequest(context = {}) {
  const jobId = runStatusIsActive(context.selectedRunStatus) ? context.selectedRunId : "";
  if (!jobId) return context.currentSession?.session_id || context.selectedSessionId || "";
  if (sessionOwnsJob(context.currentSession, jobId)) return context.currentSession.session_id;
  const session = (context.sessionRecords || []).find((candidate) => sessionOwnsJob(candidate, jobId));
  return session?.session_id || "";
}
