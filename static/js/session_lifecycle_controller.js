import { els } from './dom.js';
import { closeCompactSessions } from './layout.js';
import {
  sessionCustomTitle,
  sessionDisplaySubtitle,
  sessionDisplayTitle,
  sessionTitleDefaultText,
} from './display.js';
import {
  getAppConfig,
  modelBindingsFromControls,
  onRuntimeHarnessChanged,
  renderHarnessConfigPreview,
  resetSpecificationFileUpload,
  runtimeConfigurationError,
  selectedRuntimeHarnessSummary,
  workflowRuntimeConfigFromControls,
} from './runtime.js';
import { renderSessionListView } from './session_run_view.js';
import { sessionLatestJobId } from './run_session_state.js';
import { selectRun, state } from './state.js';
import {
  deleteSelectedSession as deleteSelectedSessionWithContext,
  openDeleteSessionModal as openDeleteSessionModalWithContext,
} from './session_lifecycle_delete.js';
import {
  loadSession as loadSessionWithContext,
  loadSessions as loadSessionsWithContext,
  refreshCurrentSessionRecord as refreshCurrentSessionRecordWithContext,
  renderSessionList as renderSessionListWithContext,
} from './session_lifecycle_loading.js';
import {
  createSessionAndStart as createSessionAndStartWithContext,
  openNewSessionModal as openNewSessionModalWithContext,
} from './session_lifecycle_new.js';
import {
  beginSessionTitleEdit as beginSessionTitleEditWithContext,
  cancelSessionTitleEdit as cancelSessionTitleEditWithContext,
  commitSessionTitleEdit as commitSessionTitleEditWithContext,
} from './session_lifecycle_title.js';

export function bindSessionLifecycleController(dependencies) {
  const context = {
    clearRunOutputs: dependencies.clearRunOutputs,
    clearTrace: dependencies.clearTrace,
    elements: els,
    closeCompactSessions,
    currentSession: () => state.currentSession,
    deleteSessionCandidateId: () => state.deleteSessionCandidateId,
    getAppConfig,
    invalidateRunLoad: () => {
      state.runLoadToken += 1;
    },
    loadRun: dependencies.loadRun,
    modelBindingsFromControls,
    nextSessionLoadToken: () => {
      state.sessionLoadToken += 1;
      return state.sessionLoadToken;
    },
    onRuntimeHarnessChanged,
    renderHarnessConfigPreview,
    renderDecisionRail: dependencies.renderDecisionRail,
    renderSessionListView,
    resetSpecificationFileUpload,
    run: dependencies.run,
    runRecords: () => state.runRecords,
    runtimeConfigurationError,
    selectedRunId: () => state.selectedRunId,
    selectedRuntimeHarnessSummary,
    selectedSessionId: () => state.selectedSessionId,
    sessionCustomTitle,
    sessionDisplaySubtitle,
    sessionDisplayTitle,
    sessionListAutoScrolledSessionId: () => state.sessionListAutoScrolledSessionId,
    sessionLatestJobId,
    sessionIsActivelyRunning: dependencies.sessionIsActivelyRunning,
    sessionLoadToken: () => state.sessionLoadToken,
    sessionRecords: () => state.sessionRecords,
    sessionTitleDefaultText,
    sessionTitleEditing: () => state.sessionTitleEditing,
    sessionTitleEditSessionId: () => state.sessionTitleEditSessionId,
    setCurrentDecisionPatches: (patches) => {
      state.currentDecisionPatches = Array.isArray(patches) ? patches : [];
    },
    setCurrentSession: (session) => {
      state.currentSession = session || null;
    },
    setDeleteSessionCandidateId: (sessionId) => {
      state.deleteSessionCandidateId = sessionId || "";
    },
    setSelectedRunId: selectRun,
    setSelectedSessionId: (sessionId) => {
      state.selectedSessionId = sessionId || null;
    },
    setSessionListAutoScrolledSessionId: (sessionId) => {
      state.sessionListAutoScrolledSessionId = sessionId || "";
    },
    setSessionRecords: (sessions) => {
      state.sessionRecords = Array.isArray(sessions) ? sessions : [];
    },
    setSessionTitleEditing: (editing) => {
      state.sessionTitleEditing = Boolean(editing);
    },
    setSessionTitleEditSessionId: (sessionId) => {
      state.sessionTitleEditSessionId = sessionId || "";
    },
    setStatus: dependencies.setStatus,
    updateDiagramControlState: dependencies.updateDiagramControlState,
    updateRuntimeRunControls: dependencies.updateRuntimeRunControls,
    updateSessionWorkspace: dependencies.updateSessionWorkspace,
    workflowRuntimeConfigFromControls,
  };

  function renderSessionList() {
    return renderSessionListWithContext(context);
  }
  function loadSessions() {
    return loadSessionsWithContext(context);
  }
  function loadSession(sessionId, options = {}) {
    return loadSessionWithContext(context, sessionId, options);
  }
  function refreshCurrentSessionRecord(options = {}) {
    return refreshCurrentSessionRecordWithContext(context, options);
  }

  const titleContext = { ...context, loadSessions };
  const deleteContext = { ...context, loadSession, loadSessions, renderSessionList };
  const newContext = { ...context, loadSessions };

  return Object.freeze({
    beginSessionTitleEdit: () => beginSessionTitleEditWithContext(titleContext),
    cancelSessionTitleEdit: () => cancelSessionTitleEditWithContext(titleContext),
    commitSessionTitleEdit: () => commitSessionTitleEditWithContext(titleContext),
    createSessionAndStart: () => createSessionAndStartWithContext(newContext),
    deleteSelectedSession: () => deleteSelectedSessionWithContext(deleteContext),
    loadSession,
    loadSessions,
    openDeleteSessionModal: () => openDeleteSessionModalWithContext(deleteContext),
    openNewSessionModal: () => openNewSessionModalWithContext(newContext),
    refreshCurrentSessionRecord,
  });
}
