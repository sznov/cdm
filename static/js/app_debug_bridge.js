// @ts-check

/** @typedef {import("../../frontend/src/run_contracts.js").AppDebugBridge} AppDebugBridge */
/** @typedef {import("../../frontend/src/run_contracts.js").AppDebugSnapshot} AppDebugSnapshot */
/** @typedef {import("../../frontend/src/run_contracts.js").DebugRunStateSnapshot} DebugRunStateSnapshot */
/** @typedef {import("../../frontend/src/run_contracts.js").RunState} RunState */

import {
  beginRunOperation,
  finishRunOperation,
  selectRun,
  state,
} from "./state.js";

/** @param {RunState} runState @returns {DebugRunStateSnapshot} */
function copyRunState(runState) {
  return {
    runId: runState.runId,
    status: runState.status,
    phase: runState.phase,
    output: runState.output,
    trace: runState.trace,
    connectionState: runState.connectionState,
    lastAppliedSequence: runState.lastAppliedSequence,
    error: runState.error,
    pendingOperation: runState.pendingOperation ? { ...runState.pendingOperation } : null,
  };
}

/**
 * @param {object} [target]
 * @returns {AppDebugBridge}
 */
export function installAppDebugBridge(target = globalThis) {
  /** @type {AppDebugBridge} */
  const bridge = Object.freeze({
    beginRunOperation,
    finishRunOperation,
    /** @param {string} runId */
    selectRun(runId) {
      selectRun(runId);
    },
    /** @returns {AppDebugSnapshot} */
    stateSnapshot() {
      const snapshot = {
        selectedRunId: state.selectedRunId,
        runsById: Object.fromEntries(
          Object.entries(state.runsById).map(([runId, runState]) => [runId, copyRunState(runState)]),
        ),
      };
      // The browser-test seam must never hand out references to live run state.
      return structuredClone(snapshot);
    },
  });
  Object.defineProperty(target, "__CDMAPP_DEBUG__", {
    configurable: true,
    enumerable: false,
    value: bridge,
    writable: false,
  });
  return bridge;
}
