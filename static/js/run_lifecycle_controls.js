import {
  cancelRunRequest,
  getRun,
} from './runs.js';
import { runActionBlocked } from './state.js';

export async function cancelRun(context, jobId) {
  if (!jobId) {
    context.setStatus("Select an active run before stopping it.");
    return;
  }
  context.setStatus(`Stopping ${context.shortRunId(jobId)}...`);
  const payload = await cancelRunRequest(jobId);
  if (payload.cancelled) {
    context.setStatus(
      payload.persistence_degraded
        ? payload.warning || `Stopped ${context.shortRunId(jobId)}, but local recovery is required.`
        : `Stop requested for ${context.shortRunId(jobId)}.`,
    );
  } else {
    context.setStatus(`${context.shortRunId(jobId)} is already ${payload.status || "finished"}.`);
  }
  await context.loadRuns();
}

export async function stopActiveRun(context) {
  if (context.selectedRunId()) {
    try {
      await cancelRun(context, context.selectedRunId());
      return;
    } catch (error) {
      console.warn("Backend cancellation failed.", error);
      context.setStatus(`Could not stop the selected run: ${error.message}`);
      return;
    }
  }
  context.setStatus("Select an active run before stopping it.");
}

export async function retrySelectedRun(context) {
  if (runActionBlocked(context.selectedRunId())) {
    context.setStatus("Wait for the current operation on this run before retrying it.");
    return;
  }
  if (!context.selectedRunId()) {
    context.setStatus("Select a run in the Runs panel first.");
    return;
  }
  const payload = await getRun(context.selectedRunId());
  const runRecord = payload.run || {};
  await context.applyRunRequestToControls(runRecord);
  context.setStatus(`Retrying ${context.shortRunId(context.selectedRunId())} as a new run...`);
  await context.run({ retryOfJobId: context.selectedRunId(), retryRunRecord: runRecord });
}

export async function resumeSelectedRun(context) {
  if (runActionBlocked(context.selectedRunId())) {
    context.setStatus("Wait for the current operation on this run before resuming it.");
    return;
  }
  if (!context.selectedRunId()) {
    context.setStatus("Select a run in the Runs panel first.");
    return;
  }
  const payload = await getRun(context.selectedRunId());
  const runRecord = payload.run || {};
  if (!runRecord.resumable && !payload.summary?.resumable) {
    context.setStatus("Selected run is not resumable.");
    return;
  }
  if (!runRecord.resume_checkpoint_stage && !payload.summary?.resume_checkpoint_stage) {
    context.setStatus("Selected run has no sane checkpoint to resume from. Start a fresh run first; newer runs will save checkpoints.");
    return;
  }
  await context.applyRunRequestToControls(runRecord);
  context.setStatus(`Resuming ${context.shortRunId(context.selectedRunId())} from its latest sane checkpoint...`);
  await context.run({ resumeFromJobId: context.selectedRunId(), resumeRunRecord: runRecord });
}
