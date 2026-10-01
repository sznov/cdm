import { getRun } from './runs.js';
import {
  applyFinalRunResult,
  applyRunSummaryStatus,
} from './run_lifecycle_status.js';
import { requiredRecordedRuntimeHarnessId } from './runtime_request_config.js';

function runHasFinalResult(run = {}) {
  const finalResult = run.result || {};
  return Boolean(finalResult.working_model || finalResult.structured_model || finalResult.plantuml);
}

export function runTraceLoadingStatusText(context, run = {}, summary = {}, stillActive = false) {
  if (stillActive) return "Loading active run trace...";
  const terminalStatusText = context.terminalRunStatusText(run, summary, {
    selectedRunStatus: context.selectedRunStatus(),
    selectedRunId: context.selectedRunId(),
  });
  if (terminalStatusText) return terminalStatusText;
  const startedAt = context.formatLocalTime(run.started_at_utc);
  if (runHasFinalResult(run)) return `Loaded final model from ${startedAt}. Loading trace in background...`;
  return `Loaded run from ${startedAt}. Loading trace in background...`;
}

export async function loadRun(context, jobId) {
  if (!jobId) return;
  context.saveDiagramViewportForRun?.(context.selectedRunId?.());
  const loadToken = context.nextRunLoadToken();
  const fetchStarted = context.perfStart();
  context.setStatus(`Loading run ${context.shortRunId(jobId)}...`);
  const payload = await getRun(jobId, { includeTrace: false });
  if (loadToken !== context.runLoadToken()) return;
  context.perfLog("archive run summary fetch", fetchStarted, { jobId });
  const run = payload.run || {};
  const runtimeHarnessId = requiredRecordedRuntimeHarnessId(run, "load this archived run");
  const harnessTemplate = run.agent_graph ||
    (await context.fetchHarnessTemplate(runtimeHarnessId));
  if (loadToken !== context.runLoadToken()) return;
  const loadingRunId = run.job_id || jobId;
  context.setSelectedRunId(loadingRunId);
  context.setSelectedRunStatus(loadingRunId, run.status || payload.summary?.status || context.selectedRunStatus());
  if (run.session_id && !context.selectedSessionId()) context.setSelectedSessionId(run.session_id);
  context.setRuntimeHarness(context.clone(harnessTemplate));
  context.updateRuntimeHarnessBadge();
  context.setTraceLoadingRunId(loadingRunId);
  try {
    await context.observeRun(loadingRunId, {
      snapshot: payload,
      forceHydrate: true,
      rebuildPresentation: true,
    });
    if (loadToken !== context.runLoadToken() || context.selectedRunId() !== loadingRunId) return;
    const stillActive = applyRunSummaryStatus(context, payload.summary || run, loadingRunId);
    applyFinalRunResult(context, loadingRunId, run);
    context.updateDecisionPatches(payload.decision_patches || run.decision_patches || []);
    context.renderRunList();
    context.renderSequence();
    context.renderTraceInspector();
    context.updateRetryRunControls();
    context.updateCorrectionChatControls();
    context.updateQuestionChatControls();
    context.updateUnifiedChatControls();
    context.refreshModelOutputMarkdown();
    context.updateSessionWorkspace();
    context.setStatus(runTraceLoadingStatusText(context, run, payload.summary, stillActive));
  } finally {
    if (loadToken === context.runLoadToken() && context.traceLoadingRunId() === loadingRunId) {
      context.setTraceLoadingRunId("");
    }
  }
}
