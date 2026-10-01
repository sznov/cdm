import {
  formatLocalTime,
} from './format.js';
import { providerName } from './runtime.js';

export function handleRunStartEvent(context, event, payload) {
  if (event !== "start") return false;
  const isReplay = payload.__replay && context.loadingArchivedRun();
  context.setLastRunTerminalStatus(null);
  const runtimeName = payload.runtime_harness_name || context.runtimeHarness()?.name || payload.runtime_harness_id || "runtime";
  const provider = payload.provider || providerName();
  const endpointClass = String(payload.endpoint_class || "");
  const endpointDetail = endpointClass && endpointClass !== "provider_default"
    ? ` (${endpointClass.replaceAll("_", " ")} endpoint)`
    : "";
  context.setStatus(`Running ${runtimeName} with ${payload.model} via ${provider}${endpointDetail}`);
  if (context.elements.jobInfo) context.elements.jobInfo.textContent = `Job ${payload.job_id} | logs: ${payload.model_call_log_dir}`;
  if (context.elements.runIdBadge) {
    context.elements.runIdBadge.hidden = true;
    context.elements.runIdBadge.textContent = formatLocalTime(payload.started_at_utc || payload.__trace_timestamp_utc);
  }
  if (!isReplay) {
    context.collapseSpecificationPanel();
    context.setModelOutputExpanded(false);
  }
  context.setRightRailTab("progress");
  if (!isReplay) context.setSelectedRunStatus("running");
  if (payload.session_id) {
    const session = context.currentSession();
    if (!isReplay && session?.session_id === payload.session_id) {
      const jobs = Array.isArray(session.job_ids) ? session.job_ids : [];
      if (payload.job_id && !jobs.includes(payload.job_id)) jobs.push(payload.job_id);
      session.job_ids = jobs;
      session.active_job_id = payload.job_id;
      session.status = "running";
      context.updateSessionWorkspace();
    }
  }
  if (!payload.__replay && !context.loadingArchivedRun()) {
    context.loadRuns().catch((error) => console.warn("Could not refresh runs", error));
    context.loadSessions().catch((error) => console.warn("Could not refresh sessions", error));
  }
  context.addTraceEntry({
    event,
    agentId: "runtime",
    title: "Run started",
    summary: `${runtimeName}: ${payload.model}${endpointDetail}`,
    payload,
    status: "running",
  });
  return true;
}

export function handleCancelRequestedEvent(context, event, payload) {
  if (event !== "cancel_requested") return false;
  context.addTraceEntry({
    event,
    agentId: "runtime",
    title: "Stop requested",
    summary: payload.detail || "Cancellation requested.",
    payload,
    status: "cancelling",
  });
  return true;
}
