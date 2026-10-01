// @ts-check

import { runStatusIsActive, terminalStatusFromRunStatus } from './run_status.js';

/** @typedef {import('../../frontend/src/run_contracts.js').RunEventEnvelopeV2} RunEventEnvelopeV2 */
/** @typedef {import('../../frontend/src/run_contracts.js').RunState} RunState */
/** @typedef {import('../../frontend/src/transport_contracts.js').EventSourceFactory} EventSourceFactory */
/** @typedef {import('../../frontend/src/transport_contracts.js').EventSourceLike} EventSourceLike */
/** @typedef {import('../../frontend/src/transport_contracts.js').RunConnectionState} RunConnectionState */
/** @typedef {import('../../frontend/src/transport_contracts.js').RunObservationController} RunObservationController */
/** @typedef {import('../../frontend/src/transport_contracts.js').RunObservationControllerOptions} RunObservationControllerOptions */
/** @typedef {import('../../frontend/src/transport_contracts.js').RunObserveOptions} RunObserveOptions */
/** @typedef {import('../../frontend/src/transport_contracts.js').RunRouteResult} RunRouteResult */
/** @typedef {import('../../frontend/src/transport_contracts.js').RunSnapshot} RunSnapshot */
/** @typedef {import('../../frontend/src/transport_contracts.js').RunSnapshotProjection} RunSnapshotProjection */
/** @typedef {Omit<RunState, 'pendingOperation' | 'viewport'>} RunObservationRollbackState */
/** @typedef {{source: EventSourceLike, eventsUrl: string, closed: boolean}} EventSourceEntry */

class RunEventContractError extends Error {}

/** @param {unknown} error */
function errorMessage(error) {
  return error instanceof Error ? (error.message || String(error)) : String(error);
}

/**
 * @param {string} eventsUrl
 * @param {number} after
 */
function eventUrlWithCursor(eventsUrl, after) {
  const separator = String(eventsUrl || "").includes("?") ? "&" : "?";
  return `${eventsUrl}${separator}after=${encodeURIComponent(String(Math.max(0, Number(after) || 0)))}`;
}

/** @type {EventSourceFactory} */
function defaultEventSourceFactory(url) {
  return new EventSource(url);
}

/**
 * @param {RunSnapshot} [snapshot]
 * @returns {RunSnapshotProjection}
 */
function snapshotProjectionWithoutHistoryCursor(snapshot = {}) {
  const projection = { ...snapshot };
  delete projection.snapshot_sequence;
  delete projection.trace;
  if (snapshot.run && typeof snapshot.run === "object") {
    projection.run = { ...snapshot.run };
    delete projection.run.snapshot_sequence;
  }
  return /** @type {RunSnapshotProjection} */ (projection);
}

/**
 * @param {RunState} runState
 * @returns {RunObservationRollbackState}
 */
function captureRunState(runState) {
  const {
    pendingOperation: _pendingOperation,
    viewport: _viewport,
    ...ownedState
  } = runState;
  return {
    ...ownedState,
    trace: [...runState.trace],
    presentationTrace: [...runState.presentationTrace],
    artifacts: { ...runState.artifacts },
  };
}

/**
 * @param {RunState} runState
 * @param {RunObservationRollbackState} snapshot
 */
function restoreRunState(runState, snapshot) {
  Object.assign(runState, snapshot, {
    trace: [...snapshot.trace],
    presentationTrace: [...snapshot.presentationTrace],
    artifacts: { ...snapshot.artifacts },
  });
}

/**
 * @param {RunObservationControllerOptions} [options]
 * @returns {RunObservationController}
 */
export function createRunObservationController(
  options = /** @type {RunObservationControllerOptions} */ ({}),
) {
  const eventSourceFactory = options.eventSourceFactory || defaultEventSourceFactory;
  const getRunSnapshot = options.getRunSnapshot;
  const getRunTracePage = options.getRunTracePage;
  const getRunState = options.getRunState;
  const hydrateRunSnapshot = options.hydrateRunSnapshot;
  const routeEnvelope = options.routeEnvelope;
  const routeHistoryEnvelope = options.routeHistoryEnvelope || routeEnvelope;
  const rebuildPresentation = options.rebuildPresentation || (async () => {});
  const onConnectionChange = options.onConnectionChange || (() => {});
  const onTerminal = options.onTerminal || (() => {});
  /** @type {Map<string, EventSourceEntry>} */
  const sources = new Map();
  /** @type {Map<string, Promise<RunState | null>>} */
  const pendingObservations = new Map();

  /**
   * @param {string} runId
   * @param {number} after
   * @param {number} through
   * @param {RunSnapshot | null} snapshot
   */
  async function hydratePersistedHistory(runId, after, through, snapshot) {
    if (typeof getRunTracePage !== "function") return after;
    let cursor = after;
    let continuationCursor = null;
    const sessionId = snapshot?.run?.session_id || snapshot?.summary?.session_id || null;
    while (cursor < through) {
      const page = await getRunTracePage(runId, {
        ...(continuationCursor ? { cursor: continuationCursor } : { after: cursor }),
        limit: Math.min(500, through - cursor),
      });
      const records = Array.isArray(page?.trace) ? page.trace : [];
      let advanced = false;
      for (const record of records) {
        const sequence = Number(record?.sequence);
        if (!Number.isInteger(sequence) || sequence <= cursor || sequence > through) continue;
        const result = routeHistoryEnvelope({
          schema_version: 2,
          run_id: runId,
          session_id: sessionId,
          sequence,
          type: record.type || record.event || "unknown",
          timestamp_utc: record.timestamp_utc || "",
          payload: record.payload || {},
        });
        if (result.reason === "invalid") {
          throw new RunEventContractError(
            `Persisted run event at sequence ${sequence} violates the v2 transport contract.`,
          );
        }
        if (result.reason === "gap") return getRunState(runId).lastAppliedSequence;
        cursor = sequence;
        advanced = true;
      }
      continuationCursor = typeof page?.next_cursor === "string" ? page.next_cursor : null;
      if (!advanced || !page?.has_more) break;
    }
    return getRunState(runId).lastAppliedSequence;
  }

  const hydrateHistory = options.hydrateHistory || hydratePersistedHistory;

  /**
   * @param {string} runId
   * @param {RunConnectionState} connectionState
   * @param {string | null | undefined} [error]
   */
  function setConnection(runId, connectionState, error = undefined) {
    const runState = getRunState(runId);
    runState.connectionState = connectionState;
    if (error !== undefined) runState.error = error;
    onConnectionChange(runId, runState);
  }

  /**
   * @param {string} runId
   * @param {RunConnectionState | null} [connectionState]
   */
  function closeSource(runId, connectionState = null) {
    const entry = sources.get(runId);
    if (entry) {
      entry.closed = true;
      entry.source.close();
      sources.delete(runId);
    }
    if (connectionState) setConnection(runId, connectionState);
  }

  /**
   * @param {string} runId
   * @param {string} eventsUrl
   */
  function reconnectFromDurableCursor(runId, eventsUrl) {
    closeSource(runId);
    setConnection(runId, "reconnecting", getRunState(runId).error);
    Promise.resolve().then(() => {
      if (sources.has(runId)) return;
      connect(runId, eventsUrl, getRunState(runId).lastAppliedSequence);
    });
  }

  /**
   * @param {string} runId
   * @param {string} eventsUrl
   * @param {number} after
   * @returns {EventSourceLike | null}
   */
  function connect(runId, eventsUrl, after) {
    if (!runId || !eventsUrl || sources.has(runId)) return sources.get(runId)?.source || null;
    const source = eventSourceFactory(eventUrlWithCursor(eventsUrl, after));
    const entry = { source, eventsUrl, closed: false };
    sources.set(runId, entry);
    setConnection(runId, "connecting");

    source.onopen = () => {
      if (sources.get(runId) !== entry || entry.closed) return;
      setConnection(runId, "connected", null);
    };
    source.onmessage = (message) => {
      if (sources.get(runId) !== entry || entry.closed) return;
      /** @type {RunEventEnvelopeV2} */
      let envelope;
      try {
        const parsed = JSON.parse(message.data);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new Error("Run event is not an object.");
        }
        envelope = /** @type {RunEventEnvelopeV2} */ (parsed);
      } catch (error) {
        setConnection(runId, "desynced", `Invalid run event: ${errorMessage(error)}`);
        reconnectFromDurableCursor(runId, eventsUrl);
        return;
      }
      if (String(envelope?.run_id || "") !== runId) {
        setConnection(runId, "desynced", `Received an event for ${envelope?.run_id || "an unknown run"}.`);
        reconnectFromDurableCursor(runId, eventsUrl);
        return;
      }
      const result = routeEnvelope(envelope);
      if (result.reason === "invalid") {
        closeSource(runId);
        setConnection(
          runId,
          "desynced",
          `Run event at sequence ${Number(envelope.sequence) || "unknown"} violates the v2 transport contract.`,
        );
        return;
      }
      if (result.reason === "gap") {
        reconnectFromDurableCursor(runId, eventsUrl);
        return;
      }
      if (result.terminal) {
        closeSource(runId, "closed");
        Promise.resolve(onTerminal(runId, envelope)).catch((error) => {
          console.warn("Could not refresh records after terminal run event", error);
        });
      }
    };
    source.onerror = () => {
      if (sources.get(runId) !== entry || entry.closed) return;
      // Native EventSource reconnects and sends Last-Event-ID automatically.
      setConnection(runId, "reconnecting", getRunState(runId).error);
    };
    return source;
  }

  /**
   * @param {string} runId
   * @param {RunObserveOptions} [observeOptions]
   * @returns {Promise<RunState | null>}
   */
  async function observeRunInternal(runId, observeOptions = {}) {
    const normalizedRunId = String(runId || "").trim();
    if (!normalizedRunId) return null;
    if (sources.has(normalizedRunId) && !observeOptions.forceHydrate) {
      return getRunState(normalizedRunId);
    }
    const eventsUrl = observeOptions.eventsUrl || `/api/runs/${encodeURIComponent(normalizedRunId)}/events`;
    const priorSource = sources.get(normalizedRunId) || null;
    const initialState = getRunState(normalizedRunId);
    const rollbackState = captureRunState(initialState);
    let observedStatus = rollbackState.status;
    try {
      if (observeOptions.forceHydrate) closeSource(normalizedRunId);
      let snapshot = observeOptions.snapshot || null;
      if (!snapshot && observeOptions.hydrate !== false) {
        snapshot = await getRunSnapshot(
          observeOptions.snapshotUrl || `/api/runs/${encodeURIComponent(normalizedRunId)}?include_trace=false`,
          normalizedRunId,
        );
      }
      const existingState = getRunState(normalizedRunId);
      const snapshotSequence = Number(snapshot?.snapshot_sequence ?? snapshot?.run?.snapshot_sequence);
      const staleSnapshot = snapshot && Number.isInteger(snapshotSequence)
        && snapshotSequence < existingState.lastAppliedSequence;
      if (snapshot && !staleSnapshot) {
        hydrateRunSnapshot(snapshotProjectionWithoutHistoryCursor(snapshot));
      }
      observedStatus = getRunState(normalizedRunId).status
        || snapshot?.run?.status
        || snapshot?.summary?.status
        || observedStatus;
      if (!staleSnapshot && Number.isInteger(snapshotSequence) && snapshotSequence > existingState.lastAppliedSequence) {
        await hydrateHistory(
          normalizedRunId,
          existingState.lastAppliedSequence,
          snapshotSequence,
          snapshot,
        );
      }
      const runState = getRunState(normalizedRunId);
      if (!runState) return null;
      const historyReachedSnapshot = !Number.isInteger(snapshotSequence)
        || runState.lastAppliedSequence >= snapshotSequence;

      const status = runState.status || snapshot?.run?.status || snapshot?.summary?.status || "";
      if (!historyReachedSnapshot) {
        runState.connectionState = "desynced";
        runState.error = `Run history stopped at sequence ${runState.lastAppliedSequence}; expected ${snapshotSequence}.`;
      }
      if (observeOptions.rebuildPresentation) {
        await rebuildPresentation(normalizedRunId, runState.trace, snapshot);
      }
      if (historyReachedSnapshot && terminalStatusFromRunStatus(status)) {
        closeSource(normalizedRunId, "closed");
        return runState;
      }
      if (historyReachedSnapshot && status && !runStatusIsActive(status)) return runState;

      connect(normalizedRunId, eventsUrl, runState.lastAppliedSequence);
      return runState;
    } catch (error) {
      const runState = getRunState(normalizedRunId);
      restoreRunState(runState, rollbackState);
      const detail = `Run hydration failed: ${errorMessage(error)}`;
      const shouldReconnect = !(error instanceof RunEventContractError) && (
        Boolean(priorSource)
        || runStatusIsActive(rollbackState.status)
        || runStatusIsActive(observedStatus)
      );
      if (shouldReconnect) {
        try {
          connect(normalizedRunId, priorSource?.eventsUrl || eventsUrl, rollbackState.lastAppliedSequence);
        } catch (reconnectError) {
          console.warn("Could not reconnect run after hydration failure", reconnectError);
        }
      }
      setConnection(normalizedRunId, "desynced", detail);
      throw error;
    }
  }

  /**
   * @param {string} runId
   * @param {RunObserveOptions} [observeOptions]
   * @returns {Promise<RunState | null>}
   */
  function observeRun(runId, observeOptions = {}) {
    const normalizedRunId = String(runId || "").trim();
    if (!normalizedRunId) return Promise.resolve(null);
    const pending = pendingObservations.get(normalizedRunId);
    if (pending) {
      if (!observeOptions.forceHydrate) return pending;
      return pending.then(() => observeRun(normalizedRunId, observeOptions));
    }
    const observation = observeRunInternal(normalizedRunId, observeOptions)
      .finally(() => pendingObservations.delete(normalizedRunId));
    pendingObservations.set(normalizedRunId, observation);
    return observation;
  }

  /** @returns {void} */
  function closeAll() {
    for (const runId of [...sources.keys()]) closeSource(runId, "idle");
  }

  return {
    closeAll,
    closeRun: closeSource,
    isObserving: (runId) => sources.has(String(runId || "")),
    observeRun,
    observedRunIds: () => [...sources.keys()],
  };
}

export { eventUrlWithCursor };
