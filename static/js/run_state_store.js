// @ts-check

/** @typedef {import("../../frontend/src/run_contracts.js").ConnectionState} ConnectionState */
/** @typedef {import("../../frontend/src/run_contracts.js").DiagramViewport} DiagramViewport */
/** @typedef {import("../../frontend/src/run_contracts.js").EventAdmission} EventAdmission */
/** @typedef {import("../../frontend/src/run_contracts.js").JsonObject} JsonObject */
/** @typedef {import("../../frontend/src/run_contracts.js").JsonValue} JsonValue */
/** @typedef {import("../../frontend/src/run_contracts.js").PendingRunOperation} PendingRunOperation */
/** @typedef {import("../../frontend/src/run_contracts.js").RunEventEnvelopeV2} RunEventEnvelopeV2 */
/** @typedef {import("../../frontend/src/run_contracts.js").RunEventReductionOptions} RunEventReductionOptions */
/** @typedef {import("../../frontend/src/run_contracts.js").RunSnapshot} RunSnapshot */
/** @typedef {import("../../frontend/src/run_contracts.js").RunState} RunState */
/** @typedef {import("../../frontend/src/run_contracts.js").RunStateSeed} RunStateSeed */
/** @typedef {import("../../frontend/src/run_contracts.js").RunStateStore} RunStateStore */
/** @typedef {import("../../frontend/src/run_contracts.js").RunStatus} RunStatus */
/** @typedef {import("../../frontend/src/run_contracts.js").SnapshotTraceRecord} SnapshotTraceRecord */
/** @typedef {import("../../frontend/src/run_contracts.js").StructuredModel} StructuredModel */

/** @type {Readonly<Partial<Record<string, RunStatus>>>} */
const TERMINAL_EVENT_STATUSES = Object.freeze({
  cancelled: "cancelled",
  done: "completed",
  error: "failed",
});

const RUN_STATUSES = new Set([
  "",
  "created",
  "queued",
  "running",
  "cancelling",
  "completed",
  "done",
  "failed",
  "error",
  "cancelled",
  "canceled",
  "interrupted",
]);
const CONNECTION_STATES = new Set([
  "idle",
  "connecting",
  "connected",
  "reconnecting",
  "desynced",
  "closed",
]);
const RUN_OPERATION_KINDS = new Set(["correction", "correction_sequence", "decision", "operation", "question"]);

/**
 * @param {unknown} value
 * @returns {value is Record<string, unknown>}
 */
function isObject(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

/**
 * @param {unknown} value
 * @param {string} key
 */
function hasOwn(value, key) {
  return isObject(value) && Object.prototype.hasOwnProperty.call(value, key);
}

/** @param {unknown} value */
function normalizedRunId(value) {
  return typeof value === "string" ? value.trim() : "";
}

/**
 * @param {unknown} source
 * @param {readonly string[]} keys
 * @returns {unknown}
 */
function firstDefined(source, keys) {
  if (!isObject(source)) return undefined;
  for (const key of keys) {
    if (hasOwn(source, key) && source[key] !== undefined) return source[key];
  }
  return undefined;
}

/**
 * @param {unknown} source
 * @param {string} [eventType]
 * @returns {JsonValue | undefined}
 */
function modelFrom(source, eventType = "") {
  const model = firstDefined(source, ["working_model", "model_snapshot"]);
  if (model !== undefined) return /** @type {JsonValue} */ (model);
  return eventType === "working_model"
    ? /** @type {JsonValue | undefined} */ (firstDefined(source, ["model"]))
    : undefined;
}

/** @param {readonly unknown[]} [trace] */
function sequenceFromTrace(trace = []) {
  let latest = 0;
  for (const entry of trace) {
    const sequence = Number(isObject(entry) ? entry.sequence : undefined);
    if (Number.isInteger(sequence) && sequence > latest) latest = sequence;
  }
  return latest;
}

/** @param {unknown} value @returns {JsonObject} */
function jsonObjectFrom(value) {
  return isObject(value) ? /** @type {JsonObject} */ (value) : {};
}

/** @param {unknown} value @returns {RunStatus | undefined} */
function runStatusFrom(value) {
  return typeof value === "string" && RUN_STATUSES.has(value)
    ? /** @type {RunStatus} */ (value)
    : undefined;
}

/** @param {unknown} value @returns {ConnectionState | undefined} */
function connectionStateFrom(value) {
  return typeof value === "string" && CONNECTION_STATES.has(value)
    ? /** @type {ConnectionState} */ (value)
    : undefined;
}

/** @param {unknown} value @returns {string | null} */
function errorFrom(value) {
  if (value === undefined || value === null || value === "") return value === "" ? "" : null;
  return typeof value === "string" ? value : String(value);
}

/** @param {unknown} value @returns {PendingRunOperation | null} */
function pendingOperationFrom(value) {
  if (
    !isObject(value)
    || typeof value.id !== "string"
    || typeof value.kind !== "string"
    || !RUN_OPERATION_KINDS.has(value.kind)
    || typeof value.startedAt !== "number"
  ) return null;
  return /** @type {PendingRunOperation} */ ({
    id: value.id,
    kind: value.kind,
    startedAt: value.startedAt,
  });
}

/**
 * @param {unknown} runId
 * @param {RunStateSeed} [seed]
 * @returns {RunState}
 */
export function createRunState(runId, seed = {}) {
  const artifacts = isObject(seed.artifacts)
    ? /** @type {NonNullable<RunStateSeed["artifacts"]>} */ (seed.artifacts)
    : {};
  const lastAppliedSequence = Number(seed.lastAppliedSequence);
  return {
    runId: normalizedRunId(runId),
    status: runStatusFrom(seed.status) ?? "",
    phase: typeof seed.phase === "string" ? seed.phase : "",
    output: typeof seed.output === "string" ? seed.output : "",
    trace: Array.isArray(seed.trace) ? [...seed.trace] : [],
    presentationTrace: Array.isArray(seed.presentationTrace) ? [...seed.presentationTrace] : [],
    artifacts: {
      workingModel: artifacts.workingModel ?? null,
      structuredModel: artifacts.structuredModel ?? null,
      plantuml: typeof artifacts.plantuml === "string" ? artifacts.plantuml : "",
      plantumlUrl: typeof artifacts.plantumlUrl === "string" ? artifacts.plantumlUrl : "",
    },
    viewport: seed.viewport ?? null,
    connectionState: connectionStateFrom(seed.connectionState) ?? "idle",
    lastAppliedSequence: Number.isInteger(lastAppliedSequence) && lastAppliedSequence >= 0
      ? lastAppliedSequence
      : 0,
    error: seed.error ?? null,
    pendingOperation: pendingOperationFrom(seed.pendingOperation),
  };
}

/** @returns {RunStateStore} */
export function createRunStateStore() {
  return {
    runsById: {},
    selectedRunId: null,
  };
}

/**
 * @param {RunStateStore} store
 * @param {unknown} runId
 * @param {RunStateSeed} [seed]
 * @returns {RunState}
 */
export function ensureRunState(store, runId, seed = {}) {
  const normalizedId = normalizedRunId(runId);
  if (!normalizedId) throw new TypeError("runId must be a non-empty string");
  if (!store.runsById[normalizedId]) {
    store.runsById[normalizedId] = createRunState(normalizedId, seed);
  }
  return store.runsById[normalizedId];
}

/** @param {RunStateStore} store @returns {RunState | null} */
export function selectedRunState(store) {
  const runId = normalizedRunId(store.selectedRunId);
  return runId ? (store.runsById[runId] || null) : null;
}

/**
 * @param {RunStateStore} store
 * @param {unknown} runId
 * @returns {RunState | null}
 */
export function selectRun(store, runId) {
  const normalizedId = normalizedRunId(runId);
  store.selectedRunId = normalizedId || null;
  return normalizedId ? (store.runsById[normalizedId] || null) : null;
}

/**
 * @param {RunSnapshot} snapshot
 * @param {RunSnapshot | import("../../frontend/src/run_contracts.js").SnapshotRunRecord} run
 */
function snapshotSequenceFrom(snapshot, run) {
  let value = firstDefined(snapshot, ["snapshot_sequence"])
    ?? firstDefined(run, ["snapshot_sequence"]);
  if (value === undefined && Array.isArray(snapshot.trace)) value = sequenceFromTrace(snapshot.trace);
  const sequence = Number(value);
  return Number.isInteger(sequence) && sequence >= 0 ? sequence : null;
}

/**
 * @param {SnapshotTraceRecord} record
 * @param {string} runId
 * @param {string | null} sessionId
 * @returns {RunEventEnvelopeV2}
 */
function snapshotEnvelope(record, runId, sessionId) {
  const sequence = Number(record.sequence);
  return {
    schema_version: 2,
    run_id: normalizedRunId(record.run_id) || runId,
    session_id: typeof record.session_id === "string" || record.session_id === null
      ? record.session_id
      : sessionId,
    sequence: Number.isInteger(sequence) && sequence >= 0 ? sequence : 0,
    type: typeof record.type === "string" ? record.type : (record.event || "unknown"),
    timestamp_utc: typeof record.timestamp_utc === "string" ? record.timestamp_utc : "",
    payload: jsonObjectFrom(record.payload),
  };
}

/**
 * @param {RunState} runState
 * @param {RunSnapshot} [snapshot]
 * @param {number | null} [snapshotSequence]
 */
function applySnapshotFields(runState, snapshot = {}, snapshotSequence = null) {
  const run = snapshot.run || snapshot;
  const summary = snapshot.summary || {};
  const result = run.result || snapshot.result || {};

  const status = runStatusFrom(firstDefined(run, ["status"]) ?? firstDefined(summary, ["status"]));
  if (status !== undefined) runState.status = status;

  const phase = firstDefined(snapshot, ["phase"]) ?? firstDefined(run, ["phase"]);
  if (typeof phase === "string") runState.phase = phase;

  const output = firstDefined(snapshot, ["output"])
    ?? firstDefined(run, ["output"])
    ?? firstDefined(result, ["output", "raw_output"]);
  if (typeof output === "string") runState.output = output;

  if (Array.isArray(snapshot.trace) && (snapshot.trace.length || !runState.trace.length)) {
    const sessionId = run.session_id || summary.session_id || null;
    runState.trace = snapshot.trace.map((record) => snapshotEnvelope(record, runState.runId, sessionId));
  }

  const model = modelFrom(result) ?? modelFrom(run) ?? modelFrom(snapshot);
  if (model !== undefined) runState.artifacts.workingModel = model ?? null;

  const structuredModel = firstDefined(result, ["structured_model"])
    ?? firstDefined(run, ["structured_model"])
    ?? firstDefined(snapshot, ["structured_model"]);
  if (structuredModel === null || isObject(structuredModel)) {
    runState.artifacts.structuredModel = /** @type {StructuredModel | null} */ (structuredModel);
  }

  const plantuml = firstDefined(result, ["plantuml"])
    ?? firstDefined(run, ["plantuml"])
    ?? firstDefined(snapshot, ["plantuml"]);
  if (typeof plantuml === "string") runState.artifacts.plantuml = plantuml;

  const plantumlUrl = firstDefined(result, ["plantuml_url"])
    ?? firstDefined(run, ["plantuml_url"])
    ?? firstDefined(snapshot, ["plantuml_url"]);
  if (typeof plantumlUrl === "string") runState.artifacts.plantumlUrl = plantumlUrl;

  const viewport = firstDefined(snapshot, ["viewport"]) ?? firstDefined(run, ["viewport"]);
  if (viewport === null || isObject(viewport)) {
    runState.viewport = /** @type {DiagramViewport | null} */ (viewport);
  }

  const connectionState = connectionStateFrom(
    firstDefined(snapshot, ["connection_state"]) ?? firstDefined(run, ["connection_state"]),
  );
  if (connectionState !== undefined) runState.connectionState = connectionState;

  const error = firstDefined(run, ["error"]) ?? firstDefined(snapshot, ["error"]);
  if (error !== undefined) runState.error = errorFrom(error);

  if (snapshotSequence !== null && snapshotSequence >= runState.lastAppliedSequence) {
    runState.lastAppliedSequence = snapshotSequence;
  }
}

/**
 * @param {RunStateStore} store
 * @param {RunSnapshot} [snapshot]
 * @returns {RunState | null}
 */
export function hydrateRunState(store, snapshot = {}) {
  const run = snapshot.run || snapshot;
  const summary = snapshot.summary || {};
  const runId = normalizedRunId(
    firstDefined(snapshot, ["run_id", "job_id"])
      ?? firstDefined(run, ["run_id", "job_id"])
      ?? firstDefined(summary, ["run_id", "job_id"]),
  );
  if (!runId) return null;
  const runState = ensureRunState(store, runId);
  const snapshotSequence = snapshotSequenceFrom(snapshot, run);
  if (snapshotSequence !== null && snapshotSequence < runState.lastAppliedSequence) return runState;
  applySnapshotFields(runState, snapshot, snapshotSequence);
  return runState;
}

/**
 * @param {RunState} runState
 * @param {string} eventType
 * @param {JsonObject} payload
 */
function applyEventStatus(runState, eventType, payload) {
  const explicitStatus = runStatusFrom(firstDefined(payload, ["status"]));
  if (explicitStatus !== undefined) {
    runState.status = explicitStatus;
  } else if (eventType === "start") {
    runState.status = "running";
  } else if (eventType === "cancel_requested") {
    runState.status = "cancelling";
  } else if (TERMINAL_EVENT_STATUSES[eventType]) {
    runState.status = TERMINAL_EVENT_STATUSES[eventType];
  }
}

/**
 * @param {RunState} runState
 * @param {string} eventType
 * @param {JsonObject} payload
 */
function applyEventOutput(runState, eventType, payload) {
  const replacement = firstDefined(payload, ["raw_output", "partial_output", "output"]);
  if (typeof replacement === "string") {
    runState.output = replacement;
    return;
  }
  const delta = firstDefined(payload, ["delta"]);
  if (typeof delta === "string" && (eventType.endsWith("_delta") || eventType === "delta")) {
    runState.output += delta;
  }
}

/**
 * @param {RunState} runState
 * @param {string} eventType
 * @param {JsonObject} payload
 */
function applyEventArtifacts(runState, eventType, payload) {
  const model = modelFrom(payload, eventType);
  if (model !== undefined) runState.artifacts.workingModel = model ?? null;
  const structuredModel = firstDefined(payload, ["structured_model"]);
  if (structuredModel === null || isObject(structuredModel)) {
    runState.artifacts.structuredModel = /** @type {StructuredModel | null} */ (structuredModel);
  }
  const plantuml = firstDefined(payload, ["plantuml"]);
  if (typeof plantuml === "string") runState.artifacts.plantuml = plantuml;
  const plantumlUrl = firstDefined(payload, ["plantuml_url"]);
  if (typeof plantumlUrl === "string") runState.artifacts.plantumlUrl = plantumlUrl;
}

/**
 * Validate and normalize an untrusted transport value before it enters a run.
 * Missing session identifiers are normalized for older persisted v2 events.
 *
 * @param {RunStateStore} store
 * @param {unknown} [envelope]
 * @returns {EventAdmission}
 */
export function inspectRunEvent(store, envelope = {}) {
  const source = isObject(envelope) ? envelope : {};
  const runId = normalizedRunId(source.run_id);
  const sequence = Number(source.sequence);
  const eventType = typeof source.type === "string" ? source.type : "";
  const timestamp = typeof source.timestamp_utc === "string" ? source.timestamp_utc : "";
  if (
    source.schema_version !== 2
    || !runId
    || !Number.isInteger(sequence)
    || sequence < 1
    || !eventType
    || !timestamp
  ) {
    return { accepted: false, reason: "invalid", runId, sequence };
  }

  const runState = ensureRunState(store, runId);
  if (sequence <= runState.lastAppliedSequence) {
    return {
      accepted: false,
      reason: "duplicate",
      runId,
      sequence,
      runState,
    };
  }
  const expectedSequence = runState.lastAppliedSequence + 1;
  if (sequence > expectedSequence) {
    runState.connectionState = "desynced";
    runState.error = `Run event sequence gap: expected ${expectedSequence} but received ${sequence}. `
      + `Reconnect from sequence ${runState.lastAppliedSequence} to replay missing events.`;
    return {
      accepted: false,
      reason: "gap",
      runId,
      sequence,
      expectedSequence,
      runState,
    };
  }

  const payload = jsonObjectFrom(source.payload);
  /** @type {RunEventEnvelopeV2} */
  const normalizedEnvelope = {
    schema_version: 2,
    run_id: runId,
    session_id: typeof source.session_id === "string" ? source.session_id : null,
    sequence,
    type: eventType,
    timestamp_utc: timestamp,
    payload,
  };
  return {
    accepted: true,
    reason: "accepted",
    runId,
    sequence,
    eventType,
    payload,
    envelope: normalizedEnvelope,
    runState,
    wasDesynced: runState.connectionState === "desynced",
  };
}

/**
 * @param {EventAdmission | null | undefined} admission
 * @returns {boolean}
 */
export function applyRunEventMetadata(admission) {
  if (!admission?.accepted) return false;
  const {
    eventType,
    payload,
    runState,
    sequence,
    wasDesynced,
  } = admission;
  runState.lastAppliedSequence = sequence;
  runState.phase = typeof payload.phase === "string" ? payload.phase : (eventType || runState.phase);
  applyEventStatus(runState, eventType, payload);

  const connectionState = connectionStateFrom(firstDefined(payload, ["connection_state"]));
  if (connectionState !== undefined) {
    runState.connectionState = connectionState;
  } else if (eventType === "start") {
    runState.connectionState = "connected";
  } else if (TERMINAL_EVENT_STATUSES[eventType]) {
    runState.connectionState = "closed";
  } else if (wasDesynced) {
    runState.connectionState = "connected";
  }

  if (eventType === "error") {
    runState.error = errorFrom(
      firstDefined(payload, ["detail", "error", "message"]) ?? "Run failed.",
    );
  } else if (eventType === "start" || wasDesynced) {
    runState.error = null;
  }
  return true;
}

/**
 * @param {EventAdmission} admission
 * @param {RunEventReductionOptions} [options]
 * @returns {boolean}
 */
export function reduceAdmittedRunEvent(admission, options = {}) {
  if (!admission.accepted) return false;
  if (!applyRunEventMetadata(admission)) return false;
  const { eventType, payload, runState, envelope } = admission;
  if (options.appendTrace !== false) runState.trace.push(envelope);
  if (options.applyPayload !== false) {
    applyEventOutput(runState, eventType, payload);
    applyEventArtifacts(runState, eventType, payload);
  }
  return true;
}

/**
 * @param {RunStateStore} store
 * @param {unknown} [envelope]
 */
export function applyRunEvent(store, envelope = {}) {
  return reduceAdmittedRunEvent(inspectRunEvent(store, envelope));
}
