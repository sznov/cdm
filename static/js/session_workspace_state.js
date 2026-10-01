import {
  activeSessionIdForCurrentRequest as deriveActiveSessionIdForCurrentRequest,
  sessionIsActivelyRunning as deriveSessionIsActivelyRunning,
} from './run_session_state.js';
import { runOperationPending, selectedRunStatus } from './state.js';

const TERMINAL_SESSION_STATUSES = new Set(["completed", "failed", "cancelled", "error"]);

export function markCurrentSessionRunStatus(context, status, jobId) {
  const { state } = context;
  if (!state.currentSession || !jobId) return false;
  if (state.currentSession.active_job_id === jobId || (state.currentSession.job_ids || []).includes(jobId)) {
    state.currentSession.status = status;
    if (TERMINAL_SESSION_STATUSES.has(status)) state.currentSession.active_job_id = null;
    const sessionRecord = (state.sessionRecords || []).find(
      (session) => session?.session_id === state.currentSession?.session_id
    );
    if (sessionRecord) {
      sessionRecord.status = status;
      if (TERMINAL_SESSION_STATUSES.has(status)) sessionRecord.active_job_id = null;
    }
    return true;
  }
  return false;
}

export function sessionIsActivelyRunning(context, session) {
  return deriveSessionIsActivelyRunning(session);
}

export function activeSessionIdForCurrentRequest(context) {
  const { state } = context;
  return deriveActiveSessionIdForCurrentRequest({
    selectedRunStatus: selectedRunStatus(),
    selectedRunId: state.selectedRunId,
    currentSession: state.currentSession,
    selectedSessionId: state.selectedSessionId,
    sessionRecords: state.sessionRecords,
  });
}

export function hasActiveRunViewLock(context) {
  const { state } = context;
  return runOperationPending(state.selectedRunId) || context.selectedRunIsActive();
}
