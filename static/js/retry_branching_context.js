import {
  shortRunId,
} from './format.js';
import {
  getRun,
} from './runs.js';
import {
  createSession,
} from './sessions.js';
import {
  sessionDisplayTitle,
} from './display.js';
import {
  modelBindingsFromControls,
  workflowRuntimeConfig,
  workflowRuntimeConfigFromControls,
} from './runtime.js';
import { state } from './state.js';

export function createRetryBranchingContext(callbacks) {
  return {
    ...callbacks,
    currentSession: () => state.currentSession,
    selectedRunId: () => state.selectedRunId,
    sessionRecords: () => state.sessionRecords,
    createSession,
    getRun,
    modelBindingsFromControls,
    sessionDisplayTitle,
    shortRunId,
    workflowRuntimeConfig,
    workflowRuntimeConfigFromControls,
    selectSession: (session) => {
      state.currentSession = session;
      state.selectedSessionId = session?.session_id || "";
    },
  };
}
