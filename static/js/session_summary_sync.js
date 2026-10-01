export function syncCurrentSessionFromList(context, sessions) {
  const selectedSessionId = context.selectedSessionId?.();
  const currentSession = context.currentSession?.();
  if (!selectedSessionId || !currentSession || currentSession.session_id !== selectedSessionId) return false;
  const summary = (sessions || []).find((session) => session?.session_id === selectedSessionId);
  if (!summary) return false;

  const nextSession = { ...currentSession };
  let changed = false;
  for (const key of ["active_job_id", "latest_job_id", "status", "title", "title_source", "updated_at_utc"]) {
    if (!Object.prototype.hasOwnProperty.call(summary, key)) continue;
    const nextValue = key === "active_job_id" ? summary[key] || null : summary[key];
    if (nextSession[key] !== nextValue) {
      nextSession[key] = nextValue;
      changed = true;
    }
  }
  if (!changed) return false;
  context.setCurrentSession(nextSession);
  context.updateSessionWorkspace?.();
  return true;
}
