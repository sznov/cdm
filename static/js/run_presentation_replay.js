import { replayTraceLog } from './trace_replay_runner.js';
import { isTraceDeltaEvent } from './trace_status.js';

function captureCanonicalRunState(runState) {
  return {
    status: runState.status,
    phase: runState.phase,
    output: runState.output,
    artifacts: {
      workingModel: runState.artifacts.workingModel,
      structuredModel: runState.artifacts.structuredModel,
      plantuml: runState.artifacts.plantuml,
      plantumlUrl: runState.artifacts.plantumlUrl,
    },
    connectionState: runState.connectionState,
    lastAppliedSequence: runState.lastAppliedSequence,
    error: runState.error,
  };
}

function restoreCanonicalRunState(runState, snapshot) {
  runState.status = snapshot.status;
  runState.phase = snapshot.phase;
  runState.output = snapshot.output;
  runState.artifacts.workingModel = snapshot.artifacts.workingModel;
  runState.artifacts.structuredModel = snapshot.artifacts.structuredModel;
  runState.artifacts.plantuml = snapshot.artifacts.plantuml;
  runState.artifacts.plantumlUrl = snapshot.artifacts.plantumlUrl;
  runState.connectionState = snapshot.connectionState;
  runState.lastAppliedSequence = snapshot.lastAppliedSequence;
  runState.error = snapshot.error;
}

export function createRunPresentationRebuilder(options = {}) {
  const state = options.state;
  const getRunState = options.getRunState;
  let replayOwner = 0;

  return async function rebuildPresentation(runId, envelopes = []) {
    if (state.selectedRunId !== runId) return { completed: false, reason: "not_selected" };
    const owner = ++replayOwner;
    const runState = getRunState(runId);
    const canonicalSnapshot = captureCanonicalRunState(runState);
    const runtimeHarness = state.runtimeHarness;
    options.clearRunOutputs();
    options.clearTrace({ keepSelectedRun: true });
    state.runtimeHarness = runtimeHarness;
    options.updateRuntimeHarnessBadge();
    state.loadingArchivedRun = true;
    try {
      return await replayTraceLog(
        envelopes.map((envelope) => ({
          sequence: envelope.sequence,
          timestamp_utc: envelope.timestamp_utc,
          event: envelope.type,
          payload: envelope.payload,
        })),
        {
          appendDelta: (delta) => options.appendReplayedGenerationDelta(runId, delta),
          batchDeltas: true,
          handleEvent: (event, payload) => options.handleEvent(event, { ...payload, job_id: runId }),
          isDeltaEvent: isTraceDeltaEvent,
          shouldContinue: () => state.selectedRunId === runId,
          yieldEvery: 50,
          yieldToBrowser: options.yieldToBrowser,
        },
      );
    } finally {
      restoreCanonicalRunState(runState, canonicalSnapshot);
      if (replayOwner === owner) state.loadingArchivedRun = false;
      if (state.selectedRunId === runId) options.updateSessionWorkspace?.();
    }
  };
}
