import {
  listRuns,
} from './runs.js';
import { runStatusIsActive } from './run_status.js';

export function renderRunList(context) {
  context.updateSessionHeaderSummary();
  context.updateRetryRunControls();
  context.renderRunListView({
    runRecords: context.runRecords(),
    selectedRunId: context.selectedRunId(),
    onLoadRun: (jobId) => context.loadRun(jobId).catch((error) => context.setStatus(`Error: ${error.message}`)),
    onCancelRun: (jobId) => context.cancelRun(jobId).catch((error) => context.setStatus(`Error: ${error.message}`)),
  });
}

export async function loadRuns(context) {
  if (!context.elements.runList) return;
  const payload = await listRuns();
  const runs = payload.runs || [];
  context.setRunRecords(runs);
  const selected = runs.find((run) => run.job_id === context.selectedRunId());
  if (selected) context.setSelectedRunStatus(selected.job_id, selected.status || context.selectedRunStatus());
  renderRunList(context);
  await Promise.allSettled(
    runs
      .filter((run) => run?.job_id && runStatusIsActive(run.status))
      .map((run) => context.observeRun(run.job_id)),
  );
}
