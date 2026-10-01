import {
  agentIdForModelCallKind,
  streamEventBase,
  STREAM_EVENT_LABELS,
} from './stream_event_metadata.js';
import { findConfiguredGenerationEvent } from './generation_stream_config.js';
import {
  appendGenerationDelta,
  completeGenerationStream,
  startGenerationStream,
} from './generation_stream_state.js';

export function handleGenericGenerationStreamEvent(event, payload = {}, context) {
  const base = streamEventBase(event);
  if (!base) return false;
  const label = STREAM_EVENT_LABELS[base];
  if (event.endsWith("_start")) {
    const agentId = payload.agent_id || agentIdForModelCallKind(base);
    context.setStatus(`${label} running...`);
    startGenerationStream(context, {
      event,
      payload,
      agentId,
      title: `${label} prompt`,
      summary: payload.summary || `Streaming ${label.toLowerCase()} output.`,
    });
    return true;
  }
  if (event.endsWith("_delta")) {
    if (!context.getTraceId()) {
      const agentId = payload.agent_id || agentIdForModelCallKind(base);
      startGenerationStream(context, {
        event: `${base}_start`,
        payload: {
          ...payload,
          inferred_start_from: event,
        },
        agentId,
        title: `${label} retry`,
        summary: "Streaming retry output.",
      });
    }
    appendGenerationDelta(context, payload.delta || "");
    return true;
  }
  if (event.endsWith("_done")) {
    context.setStatus(payload.summary || `${label} completed.`);
    completeGenerationStream(context, { event, payload, clearTraceId: true });
    return true;
  }
  return false;
}

export function handleConfiguredGenerationStreamEvent(event, payload = {}, context) {
  const config = findConfiguredGenerationEvent(event);
  if (!config) return false;
  if (event === config.start) {
    context.setStatus(config.startStatus(payload));
    startGenerationStream(context, {
      event,
      payload,
      agentId: config.agentId(payload),
      title: config.title(payload),
      summary: config.summary(payload),
    });
    return true;
  }
  if (event === config.delta) {
    appendGenerationDelta(context, payload.delta || "");
    return true;
  }
  if (event === config.done) {
    context.setStatus(config.doneStatus(payload));
    completeGenerationStream(context, { event, payload });
    return true;
  }
  return false;
}
