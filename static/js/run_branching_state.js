import { sessionOwnsJob } from "./run_session_jobs.js";

export function sourceSessionForRunRecord(runRecord, context = {}) {
  const jobId = runRecord?.job_id || context.selectedRunId || "";
  if (sessionOwnsJob(context.currentSession, jobId)) return context.currentSession;
  return (context.sessionRecords || []).find((session) => sessionOwnsJob(session, jobId)) || null;
}

export function branchSessionTitle(runRecord, context = {}) {
  const checkpointTitle = String(context.checkpointTitle || "checkpoint").trim();
  const sourceTitle =
    context.sourceTitle ||
    context.sessionDisplayTitle?.(context.sourceSession, runRecord) ||
    runRecord?.title ||
    context.shortRunId?.(runRecord?.job_id || context.selectedRunId || "") ||
    "";
  const title = `${checkpointTitle} fork - ${sourceTitle}`.trim();
  return title.length > 160 ? title.slice(0, 157).trimEnd() + "..." : title;
}
