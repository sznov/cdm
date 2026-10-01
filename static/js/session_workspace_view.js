import { formatLocalTime } from './format.js';
import {
  sessionLatestJobId,
} from './run_session_state.js';
import {
  updateSessionHeaderSummaryView,
  updateSessionTitleEditorView,
} from './session_run_view.js';
import {
  sessionIsActivelyRunning,
} from './session_workspace_state.js';

function setScrollableTextContent(element, text = "") {
  if (!element || element.textContent === text) return;
  const scrollTop = element.scrollTop;
  const scrollLeft = element.scrollLeft;
  element.textContent = text;
  element.scrollTop = scrollTop;
  element.scrollLeft = scrollLeft;
}

export function updateSessionHeaderSummary(context) {
  const { state } = context;
  updateSessionHeaderSummaryView({
    currentSession: state.currentSession,
    selectedRunId: state.selectedRunId,
    runRecords: state.runRecords,
  });
}

export function updateSessionTitleEditor(context, hasSession, selectedRun = null) {
  const { state } = context;
  updateSessionTitleEditorView({
    currentSession: state.currentSession,
    hasSession,
    isSessionActivelyRunning: (session) => sessionIsActivelyRunning(context, session),
    selectedRun,
    selectedSessionId: state.selectedSessionId,
    sessionTitleEditing: state.sessionTitleEditing,
    sessionTitleEditSessionId: state.sessionTitleEditSessionId,
  });
}

export function updateSessionWorkspace(context) {
  const { elements, state } = context;
  const ownerDocument = context.document || document;
  const hasSession = Boolean(state.currentSession);
  ownerDocument.body.classList.toggle("has-session", hasSession);
  if (elements.emptySessionState) elements.emptySessionState.hidden = hasSession;
  if (elements.diagramWorkspace) elements.diagramWorkspace.hidden = !hasSession;
  const activeJob = state.selectedRunId || sessionLatestJobId(state.currentSession);
  const selected = state.runRecords.find((run) => run.job_id === activeJob);
  if (state.sessionTitleEditing && state.sessionTitleEditSessionId !== state.selectedSessionId) {
    state.sessionTitleEditing = false;
    state.sessionTitleEditSessionId = "";
  }
  updateSessionTitleEditor(context, hasSession, selected);
  setScrollableTextContent(elements.frozenSpecText, state.currentSession?.specification || "");
  if (elements.showSpecButton) elements.showSpecButton.hidden = true;
  if (elements.runIdBadge) {
    elements.runIdBadge.hidden = true;
    elements.runIdBadge.textContent = selected?.started_at_utc
      ? formatLocalTime(selected.started_at_utc)
      : hasSession
      ? "No run yet"
      : "No session";
  }
  updateSessionHeaderSummary(context);
  context.scheduleDiagramControlPlacement();
  context.renderSessionChat();
  context.updateUnifiedChatControls();
  context.updateChatPanelVisibility();
  context.updatePhasePanel(elements.status?.textContent || "");
}
