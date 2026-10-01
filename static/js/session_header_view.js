import {
  formatLocalTime,
} from "./format.js";
import { scheduleHeaderOverflowUpdate } from "./header_layout.js";
import {
  sessionCustomTitle,
  sessionDisplaySubtitle,
  sessionDisplayTitle,
  sessionTitleDefaultText,
} from "./display.js";
import {
  sessionLatestJobId,
  sessionOwnsJob,
} from "./run_session_state.js";
import { els } from "./dom.js";

export function updateSessionHeaderSummaryView(options = {}) {
  const { currentSession, selectedRunId, runRecords = [] } = options;
  if (!els.runArchiveSummary) return;
  els.runArchiveSummary.hidden = true;
  if (!currentSession) {
    els.runArchiveSummary.textContent = "Create a session to start modeling.";
    return;
  }
  const hasCustomTitle = Boolean(sessionCustomTitle(currentSession));
  if (!hasCustomTitle) {
    els.runArchiveSummary.textContent = "";
    return;
  }
  const activeJob = selectedRunId || sessionLatestJobId(currentSession);
  const selected = runRecords.find((run) => run.job_id === activeJob);
  const subtitle = sessionDisplaySubtitle(currentSession, selected);
  if (subtitle) {
    els.runArchiveSummary.textContent = subtitle;
    els.runArchiveSummary.hidden = false;
    return;
  }
  if (selectedRunId && sessionOwnsJob(currentSession, selectedRunId)) {
    els.runArchiveSummary.textContent = selected?.started_at_utc
      ? formatLocalTime(selected.started_at_utc)
      : "Run selected.";
    els.runArchiveSummary.hidden = false;
    return;
  }
  els.runArchiveSummary.textContent = currentSession.created_at_utc
    ? formatLocalTime(currentSession.created_at_utc)
    : "No run yet.";
  els.runArchiveSummary.hidden = false;
}

export function updateSessionTitleEditorView(options = {}) {
  const {
    currentSession,
    hasSession,
    isSessionActivelyRunning,
    selectedRun = null,
    selectedSessionId,
    sessionTitleEditing,
    sessionTitleEditSessionId,
  } = options;
  const isEditing = hasSession && sessionTitleEditing && sessionTitleEditSessionId === selectedSessionId;
  const titleText = hasSession ? sessionDisplayTitle(currentSession, selectedRun) : "No session selected";
  const hasCustomTitle = hasSession && Boolean(sessionCustomTitle(currentSession));
  if (els.sessionTitle) {
    els.sessionTitle.textContent = titleText;
    els.sessionTitle.hidden = isEditing;
    els.sessionTitle.classList.toggle("session-title-datetime", hasSession && !hasCustomTitle);
    els.sessionTitle.classList.toggle("session-title-custom", hasSession && hasCustomTitle);
  }
  if (els.sessionTitleInput) {
    els.sessionTitleInput.hidden = !isEditing;
    if (isEditing && document.activeElement !== els.sessionTitleInput) {
      els.sessionTitleInput.value = sessionCustomTitle(currentSession);
      els.sessionTitleInput.placeholder = sessionTitleDefaultText(currentSession, selectedRun);
    } else if (!isEditing) {
      els.sessionTitleInput.placeholder = "";
    }
  }
  if (els.renameSessionButton) {
    els.renameSessionButton.hidden = !hasSession;
    els.renameSessionButton.disabled = !hasSession;
    els.renameSessionButton.title = isEditing ? "Cancel rename" : "Rename title";
    els.renameSessionButton.setAttribute("aria-label", isEditing ? "Cancel rename" : "Rename title");
  }
  if (els.deleteSessionButton) {
    const isActive = hasSession && isSessionActivelyRunning?.(currentSession);
    els.deleteSessionButton.hidden = !hasSession || isEditing;
    els.deleteSessionButton.disabled = !hasSession || isActive;
    els.deleteSessionButton.title = isActive ? "Stop the active run before deleting" : "Delete session";
    els.deleteSessionButton.setAttribute(
      "aria-label",
      isActive ? "Stop the active run before deleting this session" : "Delete session"
    );
  }
  scheduleHeaderOverflowUpdate();
}
