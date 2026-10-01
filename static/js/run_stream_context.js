import { els } from './dom.js';
import {
  ensureRunState,
  hydrateRunState,
  selectRun,
  setRunStatus,
  state,
} from './state.js';

export function createRunStreamContext(callbacks) {
  return {
    ...callbacks,
    elements: els,
    currentSession: () => state.currentSession,
    runtimeHarness: () => state.runtimeHarness,
    selectedRunId: () => state.selectedRunId,
    selectedSessionId: () => state.selectedSessionId,
    ensureRunState,
    hydrateRunState,
    setLastRunTerminalStatus: (status) => {
      state.lastRunTerminalStatus = status || null;
    },
    setRuntimeHarness: (harness) => {
      state.runtimeHarness = harness || null;
    },
    setSelectedRunId: (jobId) => {
      selectRun(jobId);
    },
    setSelectedRunStatus: (runId, status) => {
      setRunStatus(runId, status);
    },
    setSelectedSessionId: (sessionId) => {
      state.selectedSessionId = sessionId || null;
    },
  };
}
