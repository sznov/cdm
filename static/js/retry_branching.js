import {
  createBranchSessionForCheckpoint,
} from './retry_branching_source.js';
import {
  fetchRunRecord,
  retryTargetForTraceEntry,
} from './retry_branching_target.js';
import { runActionBlocked } from './state.js';
export {
  branchSessionTitle,
  createBranchSessionForCheckpoint,
  sourceSessionForRunRecord,
} from './retry_branching_source.js';
export {
  fetchRunRecord,
  retryTargetForTraceEntry,
} from './retry_branching_target.js';

function selectedRunId(context) {
  return context.selectedRunId?.() || "";
}

export async function retryFromTraceStep(context, entry, retryContext = {}) {
  const selectedJobId = selectedRunId(context);
  if (runActionBlocked(selectedJobId)) {
    context.setStatus("Wait for the current operation on this run before branching from a trace step.");
    return;
  }
  if (!selectedJobId || !entry) {
    context.setStatus("Select a run and a trace row first.");
    return;
  }
  if (!context.canRetryFromTraceEntry(entry)) {
    context.setStatus(context.traceRetryDisabledReason(entry));
    return;
  }
  const selectedRecord = await fetchRunRecord(context, selectedJobId);
  const target = await retryTargetForTraceEntry(context, entry, selectedRecord);
  if (target.sourceTraceIndex === null) {
    throw new Error("Cannot branch from this checkpoint because its source trace index is unknown.");
  }
  await context.applyRunRequestToControls(target.sourceRunRecord);
  const rowNumber = target.sourceTraceIndex + 1;
  const branchContext = { ...retryContext, sourceTitle: target.sourceTitle };
  context.setStatus(`Creating a fork from ${retryContext.checkpointTitle || "checkpoint"} at trace step ${rowNumber}...`);
  const branchSession = await createBranchSessionForCheckpoint(context, target.sourceRunRecord, branchContext);
  context.selectSession(branchSession);
  context.updateSessionWorkspace();
  await context.loadSessions();
  context.setStatus(`Starting fork ${branchSession.title || branchSession.session_id} from trace step ${rowNumber}...`);
  await context.run({
    resumeFromJobId: target.sourceJobId,
    resumeTraceIndex: target.sourceTraceIndex,
    resumeRunRecord: target.sourceRunRecord,
    sessionId: branchSession.session_id,
  });
}
