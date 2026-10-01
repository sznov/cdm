import {
  updateSession,
} from './sessions.js';
import {
  selectedSessionRunRecord,
} from './session_lifecycle_selection.js';

export function beginSessionTitleEdit(context) {
  const sessionId = context.selectedSessionId();
  const session = context.currentSession();
  const input = context.elements.sessionTitleInput;
  if (!sessionId || !session || !input) return;
  context.setSessionTitleEditing(true);
  context.setSessionTitleEditSessionId(sessionId);
  const selected = selectedSessionRunRecord(context);
  input.value = context.sessionCustomTitle(session);
  input.placeholder = context.sessionTitleDefaultText(session, selected);
  context.updateSessionWorkspace();
  window.requestAnimationFrame(() => {
    input.focus();
    input.select();
  });
}

export function cancelSessionTitleEdit(context) {
  if (!context.sessionTitleEditing()) return;
  context.setSessionTitleEditing(false);
  context.setSessionTitleEditSessionId("");
  context.updateSessionWorkspace();
}

export async function renameSession(context, sessionId, nextTitle) {
  const trimmed = String(nextTitle || "").trim();
  const session = context.currentSession();
  const currentTitle = context.sessionCustomTitle(session);
  const selected = selectedSessionRunRecord(context);
  const defaultTitle = context.sessionTitleDefaultText(session, selected);
  if (context.selectedSessionId() === sessionId && !currentTitle && (!trimmed || trimmed === defaultTitle)) {
    cancelSessionTitleEdit(context);
    return;
  }
  if (context.selectedSessionId() === sessionId && currentTitle === trimmed) {
    cancelSessionTitleEdit(context);
    return;
  }
  const payload = await updateSession(sessionId, { title: trimmed });
  if (context.selectedSessionId() === sessionId) {
    context.setCurrentSession(payload.session || context.currentSession());
    context.setSessionTitleEditing(false);
    context.setSessionTitleEditSessionId("");
    context.updateSessionWorkspace();
    context.setStatus(trimmed ? "Session title updated." : "Session title reset.");
  }
  await context.loadSessions();
}

export async function commitSessionTitleEdit(context) {
  if (!context.sessionTitleEditing() || !context.sessionTitleEditSessionId() || !context.elements.sessionTitleInput) return;
  await renameSession(context, context.sessionTitleEditSessionId(), context.elements.sessionTitleInput.value);
}
