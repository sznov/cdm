import {
  getSession,
  listSessions,
} from './sessions.js';
import { applySessionToControls } from './session_lifecycle_controls.js';
import { syncCurrentSessionFromList } from './session_summary_sync.js';

export function renderSessionList(context) {
  context.setSessionListAutoScrolledSessionId(context.renderSessionListView({
    isSessionActivelyRunning: context.sessionIsActivelyRunning,
    lastAutoScrolledSessionId: context.sessionListAutoScrolledSessionId(),
    selectedSessionId: context.selectedSessionId(),
    sessionRecords: context.sessionRecords(),
    onSessionSelected: (sessionId) => {
      context.closeCompactSessions();
      loadSession(context, sessionId).catch((error) => context.setStatus(`Error: ${error.message}`));
    },
  }));
}

export async function loadSessions(context, options = {}) {
  if (!context.elements.sessionList) return;
  const payload = await listSessions();
  if (
    (options.expectedLoadToken !== undefined && options.expectedLoadToken !== context.sessionLoadToken())
    || (options.expectedSessionId && options.expectedSessionId !== context.selectedSessionId())
    || (options.expectedRunId && options.expectedRunId !== context.selectedRunId())
  ) {
    return;
  }
  const sessions = payload.sessions || [];
  context.setSessionRecords(sessions);
  if (context.selectedSessionId() && !sessions.some((session) => session.session_id === context.selectedSessionId())) {
    context.setSelectedSessionId(null);
    context.setCurrentSession(null);
  }
  syncCurrentSessionFromList(context, sessions);
  renderSessionList(context);
}

export async function loadSession(context, sessionId, options = {}) {
  const loadToken = context.nextSessionLoadToken();
  const payload = await getSession(sessionId);
  if (loadToken !== context.sessionLoadToken()) return;
  const session = payload.session || null;
  context.setCurrentSession(session);
  context.setSelectedSessionId(session?.session_id || sessionId);
  if (session) await applySessionToControls(context, session);
  if (loadToken !== context.sessionLoadToken()) return;
  context.updateSessionWorkspace();
  renderSessionList(context);
  if (options.skipRunLoad) {
    context.updateSessionWorkspace();
    return;
  }
  const jobId = options.jobId || context.sessionLatestJobId(context.currentSession());
  if (jobId && !options.skipRunLoad) {
    await context.loadRun(jobId);
    if (loadToken !== context.sessionLoadToken()) return;
  } else {
    context.invalidateRunLoad();
    context.setSelectedRunId(null);
    context.clearRunOutputs({ clearRunState: false });
    context.clearTrace({ clearRunState: false });
  }
  context.updateSessionWorkspace();
}

export async function refreshCurrentSessionRecord(context, options = {}) {
  const sessionId = options.expectedSessionId || context.selectedSessionId();
  if (!sessionId) return;
  const loadToken = context.sessionLoadToken();
  const selectionStillMatches = () => (
    loadToken === context.sessionLoadToken()
    && context.selectedSessionId() === sessionId
    && (!options.expectedRunId || context.selectedRunId() === options.expectedRunId)
  );
  let payload;
  try {
    payload = await getSession(sessionId);
  } catch {
    return;
  }
  if (!selectionStillMatches()) return;
  context.setCurrentSession(payload.session || context.currentSession());
  context.updateSessionWorkspace();
  await loadSessions(context, {
    expectedLoadToken: loadToken,
    expectedRunId: options.expectedRunId,
    expectedSessionId: sessionId,
  });
  if (!selectionStillMatches()) return;
}
