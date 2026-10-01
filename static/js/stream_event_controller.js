import {
  appendGenerationDelta,
  appendReplayedGenerationDelta as appendReplayedGenerationDeltaView,
  completeGenerationStream,
  handleConfiguredGenerationStreamEvent,
  handleGenericGenerationStreamEvent,
  markGenerationInterrupted,
  startGenerationStream,
} from './generation_stream.js';
import { handleStreamChatEvent } from './stream_chat_events.js';
import {
  generationStreamContext,
  runLifecycleEventContext,
  streamChatEventContext,
  streamModelEventContext,
} from './stream_event_contexts.js';
import { handleRunLifecycleEvent } from './stream_lifecycle_events.js';
import { handleStreamModelEvent } from './stream_model_events.js';
import { isTraceDeltaEvent } from './trace_status.js';
import {
  inspectRunEvent,
  reduceAdmittedRunEvent,
} from './state.js';

const TERMINAL_RUN_EVENTS = new Set(["cancelled", "done", "error"]);

function requireRunId(value) {
  const runId = typeof value === "string" ? value.trim() : "";
  if (!runId) throw new TypeError("runId must be a non-empty string");
  return runId;
}

function eventRunId(payload = {}) {
  return requireRunId(payload?.job_id);
}

export function markCurrentGenerationInterrupted(context, runId, payload = {}) {
  markGenerationInterrupted(generationStreamContext(context, requireRunId(runId)), payload);
}

export function appendCurrentGeneration(context, runId, delta) {
  appendGenerationDelta(generationStreamContext(context, requireRunId(runId)), delta);
}

export function appendReplayedGenerationDelta(context, runId, delta) {
  appendReplayedGenerationDeltaView(generationStreamContext(context, requireRunId(runId)), delta);
}

function handleGenericStreamEvent(context, event, payload, runId) {
  return handleGenericGenerationStreamEvent(event, payload, generationStreamContext(context, runId));
}

function handleConfiguredGenerationStream(context, event, payload, runId) {
  return handleConfiguredGenerationStreamEvent(event, payload, generationStreamContext(context, runId));
}

export function startCurrentGenerationStream(context, runId, options = {}) {
  startGenerationStream(generationStreamContext(context, requireRunId(runId)), options);
}

export function completeCurrentGenerationStream(context, runId, options = {}) {
  return completeGenerationStream(generationStreamContext(context, requireRunId(runId)), options);
}

function generationActions(context, runId) {
  return {
    appendCurrentGeneration: (delta) => appendCurrentGeneration(context, runId, delta),
    completeCurrentGenerationStream: (options) => completeCurrentGenerationStream(context, runId, options),
    markCurrentGenerationInterrupted: (payload) => markCurrentGenerationInterrupted(context, runId, payload),
    startCurrentGenerationStream: (options) => startCurrentGenerationStream(context, runId, options),
  };
}

export function handleEvent(context, event, payload) {
  if (payload?.__replay && isTraceDeltaEvent(event)) return true;
  const runId = eventRunId(payload);
  const actions = generationActions(context, runId);
  if (handleRunLifecycleEvent(runLifecycleEventContext(context, actions, runId), event, payload)) return true;
  if (handleStreamChatEvent(streamChatEventContext(context, actions, runId), event, payload)) return true;
  if (handleGenericStreamEvent(context, event, payload, runId)) return true;
  if (handleConfiguredGenerationStream(context, event, payload, runId)) return true;
  if (handleStreamModelEvent(streamModelEventContext(context, actions, runId), event, payload)) return true;
  return false;
}

/**
 * Route one durable run envelope without letting view selection own execution.
 *
 * The existing event handlers are still the rich selected-run renderer. They
 * mutate the explicitly targeted normalized record, so the generic reducer
 * must not run as well for a handled selected event.
 * Unselected events take the headless reducer path and are never discarded.
 */
export function handleRunEnvelope(context, envelope = {}) {
  const admission = inspectRunEvent(envelope);
  if (!admission.accepted) {
    return {
      accepted: false,
      reason: admission.reason,
      runId: admission.runId || "",
      sequence: admission.sequence || 0,
      lastAppliedSequence: admission.runState?.lastAppliedSequence || 0,
    };
  }

  const selected = context.state.selectedRunId === admission.runId;
  let rendered = false;
  if (selected) {
    rendered = handleEvent(context, admission.eventType, {
      ...admission.payload,
      job_id: admission.runId,
      session_id: envelope.session_id || admission.payload.session_id || null,
      __event_sequence: admission.sequence,
      __trace_index: admission.sequence - 1,
      __trace_timestamp_utc: envelope.timestamp_utc,
    });
  }

  if (selected && rendered) {
    reduceAdmittedRunEvent(admission, { applyPayload: false });
  } else {
    reduceAdmittedRunEvent(admission);
  }

  return {
    accepted: true,
    reason: "accepted",
    rendered,
    runId: admission.runId,
    sequence: admission.sequence,
    terminal: TERMINAL_RUN_EVENTS.has(admission.eventType),
  };
}

export function handleHeadlessRunEnvelope(envelope = {}) {
  const admission = inspectRunEvent(envelope);
  if (!admission.accepted) return admission;
  reduceAdmittedRunEvent(admission);
  return {
    accepted: true,
    reason: "accepted",
    runId: admission.runId,
    sequence: admission.sequence,
    terminal: TERMINAL_RUN_EVENTS.has(admission.eventType),
  };
}
