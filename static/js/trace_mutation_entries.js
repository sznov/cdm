import {
  clone,
  optionalClone,
  traceEventTimestamp,
  traceTimestamp,
} from './format.js';
import {
  runtimeAgentById,
  selectedAgentForEvent,
} from './runtime_agents.js';

export function addTraceEntry(context, {
  event,
  agentId,
  title,
  summary = "",
  payload = {},
  prompt = "",
  output = "",
  status = "",
  modelSnapshot = null,
  plantuml = "",
  plantumlUrl = "",
}) {
  const entries = context.traceEntries();
  const harness = context.runtimeHarness();
  const agent = runtimeAgentById(harness, agentId) || selectedAgentForEvent(harness, event, payload);
  const traceIndex = Number.isInteger(payload?.__trace_index) ? payload.__trace_index : entries.length;
  const baseTraceId = `trace-${String(Math.max(0, traceIndex)).padStart(8, "0")}`;
  let traceId = baseTraceId;
  let collision = 2;
  while (entries.some((candidate) => candidate.id === traceId)) {
    traceId = `${baseTraceId}-${collision}`;
    collision += 1;
  }
  const implicitSnapshots = !context.loadingArchivedRun();
  const entry = {
    id: traceId,
    trace_index: traceIndex,
    event,
    agent_id: agent?.id || agentId || "runtime",
    agent_name: agent?.name || agentId || "Runtime",
    agent_snapshot: agent ? clone(agent) : null,
    title,
    summary,
    prompt,
    output,
    status,
    payload,
    timestamp_utc: traceEventTimestamp(payload),
    created_at: traceTimestamp(payload),
    working_model_snapshot: optionalClone(modelSnapshot || (implicitSnapshots ? context.currentWorkingModel() : null)),
    structured_model_snapshot: optionalClone(
      payload.structured_model || (implicitSnapshots ? context.currentStructuredModel() : null),
    ),
    plantuml_snapshot: plantuml || (implicitSnapshots ? context.currentPlantuml() : ""),
    plantuml_url: plantumlUrl || (implicitSnapshots ? context.currentPlantumlUrl() : ""),
    runtime_harness_id: harness?.id || String(payload.runtime_harness_id || ""),
  };
  entries.push(entry);
  context.syncBuildLogModalCurrentOutput(entry);
  if (!context.traceRenderingDeferred()) context.upsertTraceEntryChatBubble(entry);
  if (context.loadingArchivedRun()) {
    if (context.traceEntryVisibleForProgressFilter(entry) || !context.selectedTraceId()) context.setSelectedTraceId(entry.id);
  } else if (context.autoFollowTrace() || !context.selectedTraceId()) {
    context.setSelectedTraceId(context.latestVisibleTraceEntry()?.id || entry.id);
  }
  if (!context.traceRenderingDeferred()) {
    context.renderSequence();
    if (context.selectedTraceId() === entry.id || context.autoFollowTrace()) context.renderTraceInspector();
  }
  return entry.id;
}

export function updateTraceEntry(context, id, patch) {
  const entry = context.traceEntries().find((candidate) => candidate.id === id);
  if (!entry) return;
  Object.assign(entry, patch);
  if (!context.traceRenderingDeferred()) context.upsertTraceEntryChatBubble(entry);
  if (patch.output != null || id === context.currentGenerationTraceId()) context.scheduleModelOutputMarkdownRender();
  if (patch.output != null || id === context.currentGenerationTraceId()) context.syncBuildLogModalCurrentOutput(entry);
  if (context.traceRenderingDeferred()) return;
  context.renderSequence();
  if (context.selectedTraceId() === id) context.renderTraceInspector();
}
