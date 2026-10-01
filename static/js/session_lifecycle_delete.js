import {
  removeSession,
} from './sessions.js';
import {
  selectedSessionRunRecord,
} from './session_lifecycle_selection.js';

const DELETE_SESSION_LABEL = "Delete session";

function setDeleteSessionBusy(elements, busy) {
  const active = Boolean(busy);
  const form = elements.deleteSessionModal?.querySelector("form");
  if (form) form.setAttribute("aria-busy", String(active));
  if (!elements.confirmDeleteSessionButton) return;
  elements.confirmDeleteSessionButton.disabled = active;
  elements.confirmDeleteSessionButton.textContent = active ? "Deleting…" : DELETE_SESSION_LABEL;
}

export function openDeleteSessionModal(context) {
  const session = context.currentSession();
  const sessionId = context.selectedSessionId();
  const { elements } = context;
  if (!session || !sessionId || !elements.deleteSessionModal) return;
  if (context.sessionIsActivelyRunning(session)) {
    context.setStatus("Stop the active run before deleting this session.");
    return;
  }
  context.setDeleteSessionCandidateId(sessionId);
  const selected = selectedSessionRunRecord(context);
  const title = context.sessionDisplayTitle(session, selected);
  const subtitle = context.sessionDisplaySubtitle(session, selected);
  if (elements.deleteSessionTitle) elements.deleteSessionTitle.textContent = title || "Untitled session";
  if (elements.deleteSessionSubtitle) {
    elements.deleteSessionSubtitle.textContent = subtitle || "";
    elements.deleteSessionSubtitle.hidden = !subtitle;
  }
  if (elements.deleteSessionWarning) {
    elements.deleteSessionWarning.hidden = true;
    elements.deleteSessionWarning.textContent = "";
  }
  setDeleteSessionBusy(elements, false);
  elements.deleteSessionModal.showModal();
  requestAnimationFrame(() => elements.cancelDeleteSessionButton?.focus());
}

export function clearSelectedSessionView(context) {
  context.invalidateRunLoad();
  context.setSelectedSessionId(null);
  context.setCurrentSession(null);
  context.setSelectedRunId(null);
  context.setCurrentDecisionPatches([]);
  context.clearRunOutputs({ clearRunState: false });
  context.clearTrace({ clearRunState: false });
  context.renderSessionList();
  context.updateSessionWorkspace();
  context.renderDecisionRail();
  context.updateDiagramControlState();
}

export async function deleteSelectedSession(context) {
  const sessionId = context.deleteSessionCandidateId() || context.selectedSessionId();
  const { elements } = context;
  if (!sessionId) return;
  setDeleteSessionBusy(elements, true);
  try {
    await removeSession(sessionId);
  } catch (error) {
    const message = error.message || "Could not delete this session.";
    if (elements.deleteSessionWarning) {
      elements.deleteSessionWarning.hidden = false;
      elements.deleteSessionWarning.textContent = message || "Could not delete this session.";
    }
    setDeleteSessionBusy(elements, false);
    throw error;
  }
  if (elements.deleteSessionModal?.open) elements.deleteSessionModal.close();
  context.setDeleteSessionCandidateId("");
  const deletedCurrent = context.selectedSessionId() === sessionId;
  if (deletedCurrent) clearSelectedSessionView(context);
  await context.loadSessions();
  const sessions = context.sessionRecords();
  if (deletedCurrent && sessions.length) {
    await context.loadSession(sessions[0].session_id);
  } else if (!sessions.length) {
    clearSelectedSessionView(context);
  }
  context.setStatus("Session deleted.");
}
