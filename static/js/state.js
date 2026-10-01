// @ts-check

/** @typedef {import("../../frontend/src/run_contracts.js").EventAdmission} EventAdmission */
/** @typedef {import("../../frontend/src/run_contracts.js").PendingRunOperation} PendingRunOperation */
/** @typedef {import("../../frontend/src/run_contracts.js").RunEventReductionOptions} RunEventReductionOptions */
/** @typedef {import("../../frontend/src/run_contracts.js").RunOperationKind} RunOperationKind */
/** @typedef {import("../../frontend/src/run_contracts.js").RunSnapshot} RunSnapshot */
/** @typedef {import("../../frontend/src/run_contracts.js").RunState} RunState */
/** @typedef {import("../../frontend/src/run_contracts.js").RunStateSeed} RunStateSeed */

import {
  applyRunEventMetadata as applyStoreRunEventMetadata,
  applyRunEvent as applyStoreRunEvent,
  createRunStateStore,
  ensureRunState as ensureStoreRunState,
  hydrateRunState as hydrateStoreRunState,
  inspectRunEvent as inspectStoreRunEvent,
  reduceAdmittedRunEvent as reduceStoreAdmittedRunEvent,
  selectRun as selectStoreRun,
  selectedRunState as selectedStoreRunState,
} from './run_state_store.js';

export const DEFAULT_TRACE_RENDER_LIMIT = 150;
export const TRACE_RENDER_INCREMENT = 150;

const runStateStore = createRunStateStore();
let runOperationCounter = 0;

const baseState = {
  sessionLoadToken: 0,
  runLoadToken: 0,
  archivedReplayLastStatus: "",
  runRecords: [],
  loadingArchivedRun: false,
  runtimeHarness: null,
  selectedTraceId: null,
  autoFollowTrace: true,
  traceRenderLimit: DEFAULT_TRACE_RENDER_LIMIT,
  currentGenerationTraceId: null,
  activeCorrectionStreamChatId: "",
  currentDecisionPatches: [],
  lastRunTerminalStatus: null,
  sessionRecords: [],
  selectedSessionId: null,
  sessionListAutoScrolledSessionId: "",
  currentSession: null,
  pendingChatCorrection: "",
  modelOutputExpanded: false,
  renderingSessionTranscript: false,
  traceLoadingRunId: "",
  sessionTitleEditing: false,
  sessionTitleEditSessionId: "",
  skipNextRenameSessionClick: false,
  deleteSessionCandidateId: "",
};

export const state = Object.assign(runStateStore, baseState);

/** @param {unknown} runId @param {RunStateSeed} [seed] @returns {RunState} */
export function ensureRunState(runId, seed = {}) {
  return ensureStoreRunState(runStateStore, runId, seed);
}

/** @param {RunSnapshot} [snapshot] @returns {RunState | null} */
export function hydrateRunState(snapshot = {}) {
  return hydrateStoreRunState(runStateStore, snapshot);
}

/** @param {unknown} [envelope] */
export function applyRunEvent(envelope = {}) {
  return applyStoreRunEvent(runStateStore, envelope);
}

/** @param {unknown} [envelope] @returns {EventAdmission} */
export function inspectRunEvent(envelope = {}) {
  return inspectStoreRunEvent(runStateStore, envelope);
}

/** @param {EventAdmission | null | undefined} admission */
export function applyRunEventMetadata(admission) {
  return applyStoreRunEventMetadata(admission);
}

/** @param {EventAdmission} admission @param {RunEventReductionOptions} [options] */
export function reduceAdmittedRunEvent(admission, options = {}) {
  return reduceStoreAdmittedRunEvent(admission, options);
}

/** @param {unknown} runId @returns {RunState | null} */
export function selectRun(runId) {
  return selectStoreRun(runStateStore, runId);
}

/** @returns {RunState | null} */
export function selectedRunState() {
  return selectedStoreRunState(runStateStore);
}

/** @param {unknown} runId @returns {RunState | null} */
export function runStateById(runId) {
  const normalizedId = String(runId || "").trim();
  return normalizedId ? (state.runsById[normalizedId] || null) : null;
}

/** @returns {RunState["status"]} */
export function selectedRunStatus() {
  return selectedRunState()?.status || "";
}

/** @returns {RunState["presentationTrace"]} */
export function selectedPresentationTrace() {
  return selectedRunState()?.presentationTrace || [];
}

/** @returns {string} */
export function selectedGenerationOutput() {
  return selectedRunState()?.output || "";
}

/** @returns {RunState["artifacts"]["workingModel"]} */
export function selectedWorkingModel() {
  return selectedRunState()?.artifacts.workingModel ?? null;
}

/** @returns {RunState["artifacts"]["structuredModel"]} */
export function selectedStructuredModel() {
  return selectedRunState()?.artifacts.structuredModel ?? null;
}

/** @returns {string} */
export function selectedPlantuml() {
  return selectedRunState()?.artifacts.plantuml || "";
}

/** @returns {string} */
export function selectedPlantumlUrl() {
  return selectedRunState()?.artifacts.plantumlUrl || "";
}

/** @param {unknown} runId @param {RunState["status"] | string | null | undefined} status */
export function setRunStatus(runId, status) {
  ensureStoreRunState(runStateStore, runId).status = /** @type {RunState["status"]} */ (status || "");
}

/** @param {unknown} runId @param {unknown} output */
export function setRunOutput(runId, output) {
  ensureStoreRunState(runStateStore, runId).output = typeof output === "string" ? output : "";
}

/** @param {unknown} runId @param {unknown} model */
export function setRunWorkingModel(runId, model) {
  ensureStoreRunState(runStateStore, runId).artifacts.workingModel = /** @type {RunState["artifacts"]["workingModel"]} */ (model ?? null);
}

/** @param {unknown} runId @param {unknown} model */
export function setRunStructuredModel(runId, model) {
  ensureStoreRunState(runStateStore, runId).artifacts.structuredModel = /** @type {RunState["artifacts"]["structuredModel"]} */ (model ?? null);
}

/** @param {unknown} runId @param {unknown} plantuml */
export function setRunPlantuml(runId, plantuml) {
  ensureStoreRunState(runStateStore, runId).artifacts.plantuml = typeof plantuml === "string" ? plantuml : "";
}

/** @param {unknown} runId @param {unknown} url */
export function setRunPlantumlUrl(runId, url) {
  ensureStoreRunState(runStateStore, runId).artifacts.plantumlUrl = typeof url === "string" ? url : "";
}

/** @param {unknown} runId @param {RunState["presentationTrace"]} entries */
export function setRunPresentationTrace(runId, entries) {
  ensureStoreRunState(runStateStore, runId).presentationTrace = Array.isArray(entries) ? [...entries] : [];
}

/** @param {unknown} runId @param {import("../../frontend/src/run_contracts.js").DiagramViewport | null} viewport */
export function setRunViewport(runId, viewport) {
  ensureStoreRunState(runStateStore, runId).viewport = viewport ?? null;
}

/** @param {unknown} runId */
export function runOperationPending(runId) {
  const normalizedRunId = String(runId || "").trim();
  return Boolean(normalizedRunId && state.runsById[normalizedRunId]?.pendingOperation);
}

/**
 * Presentation replay is not an operation, but it must finish before a model
 * mutation can safely render into the selected run's compatibility view.
 *
 * @param {unknown} runId
 */
export function runActionBlocked(runId) {
  const normalizedRunId = String(runId || "").trim();
  return runOperationPending(normalizedRunId) || Boolean(
    normalizedRunId
      && state.loadingArchivedRun
      && state.selectedRunId === normalizedRunId
  );
}

/**
 * @param {unknown} runId
 * @param {RunOperationKind} kind
 * @returns {PendingRunOperation | null}
 */
export function beginRunOperation(runId, kind) {
  const runState = ensureStoreRunState(runStateStore, runId);
  if (!runState.runId || runState.pendingOperation) return null;
  runOperationCounter += 1;
  /** @type {PendingRunOperation} */
  const operation = {
    id: `${String(kind || "operation")}-${runOperationCounter}`,
    kind: kind || "operation",
    startedAt: Date.now(),
  };
  runState.pendingOperation = operation;
  return operation;
}

/** @param {unknown} runId @param {string} operationId */
export function finishRunOperation(runId, operationId) {
  const runState = ensureStoreRunState(runStateStore, runId);
  if (!runState.pendingOperation || runState.pendingOperation.id !== operationId) return false;
  runState.pendingOperation = null;
  return true;
}
