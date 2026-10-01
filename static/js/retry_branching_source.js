import {
  branchSessionTitle as deriveBranchSessionTitle,
  sourceSessionForRunRecord as deriveSourceSessionForRunRecord,
} from './run_session_state.js';
import { requiredRecordedRuntimeHarnessId } from './runtime_request_config.js';

function selectedRunId(context) {
  return context.selectedRunId?.() || "";
}

function currentSession(context) {
  return context.currentSession?.() || null;
}

function sessionRecords(context) {
  return context.sessionRecords?.() || [];
}

export function sourceSessionForRunRecord(context, runRecord) {
  return deriveSourceSessionForRunRecord(runRecord, {
    selectedRunId: selectedRunId(context),
    currentSession: currentSession(context),
    sessionRecords: sessionRecords(context),
  });
}

export function branchSessionTitle(context, runRecord, retryContext = {}) {
  return deriveBranchSessionTitle(runRecord, {
    ...retryContext,
    sourceSession: sourceSessionForRunRecord(context, runRecord),
    selectedRunId: selectedRunId(context),
    sessionDisplayTitle: context.sessionDisplayTitle,
    shortRunId: context.shortRunId,
  });
}

export async function createBranchSessionForCheckpoint(context, runRecord, retryContext = {}) {
  const effectiveSpec = runRecord?.effective_harness_run_spec || {};
  const sourceSession = sourceSessionForRunRecord(context, runRecord);
  const runtimeHarnessId = requiredRecordedRuntimeHarnessId(
    runRecord?.runtime_harness_id || effectiveSpec.harness_id
      ? runRecord
      : sourceSession,
    "branch from this run",
  );
  const sourceSessionRevision = sourceSession?.runtime_harness_id === runtimeHarnessId
    ? sourceSession?.harness_definition_revision
    : null;
  const harnessDefinitionRevision =
    runRecord?.harness_definition_revision ||
    effectiveSpec.definition_revision ||
    sourceSessionRevision ||
    null;
  const specification =
    runRecord?.specification ||
    sourceSession?.specification ||
    "";
  if (!String(specification).trim()) {
    throw new Error("Cannot fork this run because its original specification is unavailable.");
  }
  const payload = {
    title: branchSessionTitle(context, runRecord, retryContext),
    runtime_harness_id: runtimeHarnessId,
    harness_definition_revision: harnessDefinitionRevision,
    harness_runtime_config: effectiveSpec.effective_config
      ? context.workflowRuntimeConfig(effectiveSpec.effective_config)
      : context.workflowRuntimeConfigFromControls(runtimeHarnessId),
    model_bindings:
      runRecord?.model_bindings ||
      effectiveSpec.model_bindings ||
      sourceSession?.model_bindings ||
      context.modelBindingsFromControls?.(runtimeHarnessId),
    specification,
  };
  Object.keys(payload).forEach((key) => {
    if (payload[key] === null || payload[key] === undefined) delete payload[key];
  });
  const data = await context.createSession(payload);
  return data.session;
}
