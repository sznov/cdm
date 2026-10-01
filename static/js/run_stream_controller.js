import { clone } from './format.js';
import { createRun } from './runs.js';
import { prepareRunStreamRequest } from './run_stream_request.js';
import { fetchHarnessTemplate } from './runtime.js';

export async function run(context, options = {}) {
  const request = prepareRunStreamRequest(context, options);
  if (!request) return null;

  try {
    const runtimeHarness = clone(await fetchHarnessTemplate(request.runtimeId));
    const creation = await createRun(request.payload);
    const runId = creation.run_id;
    const sessionId = creation.session_id || request.payload.session_id || null;

    context.setSelectedRunId(runId);
    context.ensureRunState(runId, { status: creation.status || "queued" });
    context.setSelectedRunStatus(runId, creation.status || "queued");
    if (sessionId) context.setSelectedSessionId(sessionId);
    context.clearRunOutputs();
    context.clearTrace({ keepSelectedRun: true });
    context.setRuntimeHarness(runtimeHarness);
    context.updateRuntimeHarnessBadge();
    context.setLastRunTerminalStatus(null);
    context.setRunning(true);
    context.setStatus(`Queued ${runId}; waiting for the runtime to start...`);

    await context.observeRun(runId, {
      eventsUrl: creation.events_url,
      snapshotUrl: `${creation.snapshot_url}?include_trace=false`,
    });
    await Promise.allSettled([
      context.loadRuns(),
      context.loadSessions(),
    ]);
    return creation;
  } catch (error) {
    context.setStatus(`Error: ${error.message}`);
    context.setRunning(false);
    return null;
  }
}
