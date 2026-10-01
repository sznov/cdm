// @ts-check

/** @typedef {import('../../frontend/src/run_contracts.js').JsonObject} JsonObject */
/** @typedef {import('../../frontend/src/run_contracts.js').RunEventEnvelopeV2} RunEventEnvelopeV2 */
/** @typedef {import('../../frontend/src/transport_contracts.js').RunEnvelopeRouter} RunEnvelopeRouter */
/** @typedef {import('../../frontend/src/transport_contracts.js').RunTracePage} RunTracePage */

/** @typedef {{routeEnvelope: RunEnvelopeRouter, sessionId?: string | null}} OperationStreamOptions */

/** @typedef {{routeEnvelope: RunEnvelopeRouter, restoreClosed?: boolean}} OperationTraceSyncOptions */

import { streamSse } from "./api.js";
import { getRunTrace } from "./runs.js";
import { ensureRunState } from "./state.js";

/** @param {unknown} value @returns {value is Record<string, unknown>} */
function isObject(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

/**
 * Convert a streamed operation event into the same durable envelope used by
 * reconnectable run observation. The two reserved fields exist only on the
 * live response; they are stripped before the domain payload is reduced.
 *
 * @param {string} runId
 * @param {string} event
 * @param {unknown} value
 * @param {string | null} [sessionId]
 * @returns {RunEventEnvelopeV2 | null}
 */
export function operationEnvelopeFromEvent(runId, event, value, sessionId = null) {
  if (!isObject(value)) return null;
  const sequence = Number(value.__event_sequence);
  const timestamp = typeof value.__trace_timestamp_utc === "string"
    ? value.__trace_timestamp_utc
    : "";
  if (!runId || !event || !Number.isInteger(sequence) || sequence < 1 || !timestamp) return null;
  const payload = { ...value };
  delete payload.__event_sequence;
  delete payload.__trace_timestamp_utc;
  return {
    schema_version: 2,
    run_id: runId,
    session_id: typeof sessionId === "string" && sessionId ? sessionId : null,
    sequence,
    type: event,
    timestamp_utc: timestamp,
    payload: /** @type {JsonObject} */ (payload),
  };
}

/** @param {unknown} payload */
function streamedError(payload) {
  if (!isObject(payload)) return "Operation failed.";
  return String(payload.detail || payload.error || payload.message || "Operation failed.");
}

/**
 * @param {string} url
 * @param {string} runId
 * @param {JsonObject} payload
 * @param {{routeEnvelope: RunEnvelopeRouter, sessionId?: string | null, networkErrorMessage: string}} options
 */
async function streamOperationEvents(url, runId, payload, options) {
  const observationWasClosed = ensureRunState(runId).connectionState === "closed";
  /** @type {Error | null} */
  let operationError = null;
  /** @type {unknown} */
  let requestError = null;
  try {
    await streamSse(url, {
      payload,
      networkErrorMessage: options.networkErrorMessage,
      onEvent: (event, eventPayload) => {
        const envelope = operationEnvelopeFromEvent(runId, event, eventPayload, options.sessionId || null);
        if (!envelope) {
          operationError = new Error(
            event === "error"
              ? streamedError(eventPayload)
              : `Operation event ${event || "unknown"} has no durable trace metadata.`,
          );
          return;
        }
        const result = options.routeEnvelope(envelope);
        if (!result.accepted && !["duplicate", "gap"].includes(result.reason)) {
          operationError = new Error(
            `Operation event ${envelope.sequence} could not enter run ${runId}: ${result.reason}.`,
          );
        }
      },
    });
    if (operationError) throw operationError;
  } catch (error) {
    requestError = error;
    throw error;
  } finally {
    try {
      await syncRunOperationTrace(runId, {
        routeEnvelope: options.routeEnvelope,
        restoreClosed: observationWasClosed,
      });
    } catch (syncError) {
      if (!requestError) throw syncError;
      console.warn(`Could not reconcile the trace for failed operation on ${runId}.`, syncError);
    }
  }
}

/**
 * Replay any durable operation records not already admitted by the live
 * stream. This is normally a no-op for streamed operations and is the source
 * of truth for non-streaming decision application.
 *
 * @param {string} runId
 * @param {OperationTraceSyncOptions} options
 */
export async function syncRunOperationTrace(runId, options) {
  const runState = ensureRunState(runId);
  const restoreClosed = options.restoreClosed ?? runState.connectionState === "closed";
  let cursor = runState.lastAppliedSequence;
  let continuationCursor = null;
  while (true) {
    const page = /** @type {RunTracePage | null} */ (
      await getRunTrace(
        runId,
        continuationCursor ? { cursor: continuationCursor, limit: 500 } : { after: cursor, limit: 500 },
      )
    );
    const records = Array.isArray(page?.trace) ? page.trace : [];
    for (const record of records) {
      const sequence = Number(record?.sequence);
      if (!Number.isInteger(sequence) || sequence <= cursor) continue;
      const result = options.routeEnvelope({
        schema_version: 2,
        run_id: runId,
        session_id: typeof record.session_id === "string" ? record.session_id : null,
        sequence,
        type: record.type || record.event || "unknown",
        timestamp_utc: record.timestamp_utc || "",
        payload: record.payload || {},
      });
      if (!result.accepted && result.reason !== "duplicate") {
        throw new Error(`Persisted operation event ${sequence} could not enter run ${runId}: ${result.reason}.`);
      }
      cursor = sequence;
    }
    continuationCursor = typeof page?.next_cursor === "string" ? page.next_cursor : null;
    if (!page?.has_more || !records.length) {
      if (restoreClosed) ensureRunState(runId).connectionState = "closed";
      return cursor;
    }
  }
}

/** @param {string} jobId @param {JsonObject} payload @param {OperationStreamOptions} options */
export function streamCorrectionEvents(jobId, payload, options) {
  return streamOperationEvents(
    `/api/runs/${encodeURIComponent(jobId)}/corrections/stream`,
    jobId,
    payload,
    { ...options, networkErrorMessage: "Network error while streaming correction patch." },
  );
}

/** @param {string} jobId @param {JsonObject} payload @param {OperationStreamOptions} options */
export function streamQuestionEvents(jobId, payload, options) {
  return streamOperationEvents(
    `/api/runs/${encodeURIComponent(jobId)}/questions/stream`,
    jobId,
    payload,
    { ...options, networkErrorMessage: "Network error while streaming question." },
  );
}

/** @param {string} jobId @param {JsonObject} payload @param {OperationStreamOptions} options */
export function streamCorrectionSequenceEvents(jobId, payload, options) {
  return streamOperationEvents(
    `/api/runs/${encodeURIComponent(jobId)}/correction-sequences/stream`,
    jobId,
    payload,
    { ...options, networkErrorMessage: "Network error while streaming correction sequence." },
  );
}
