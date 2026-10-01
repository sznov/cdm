export function selectedSessionRunRecord(context) {
  const session = context.currentSession();
  const activeJob = context.selectedRunId() || context.sessionLatestJobId(session);
  return context.runRecords().find((run) => run.job_id === activeJob) || null;
}
