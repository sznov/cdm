// @ts-check

import {
  canRunSelectedRuntime,
  modelBindingsFromControls,
  runtimeConfigurationError,
  selectedRuntimeHarnessSummary,
  workflowRuntimeConfigFromControls,
} from './runtime.js';
import {
  recordedRuntimeRequestConfig,
  requiredRecordedRuntimeHarnessId,
} from './runtime_request_config.js';

/** @typedef {import('../../frontend/src/transport_contracts.js').CreateRunRequest} CreateRunRequest */
/** @typedef {import('../../frontend/src/transport_contracts.js').PreparedRunRequest} PreparedRunRequest */
/** @typedef {import('../../frontend/src/transport_contracts.js').PrepareRunOptions} PrepareRunOptions */
/** @typedef {import('../../frontend/src/transport_contracts.js').RunStreamRequestContext} RunStreamRequestContext */
/** @typedef {import('../../frontend/src/transport_contracts.js').RuntimeModelBindings} RuntimeModelBindings */
/** @typedef {import('../../frontend/src/transport_contracts.js').RuntimeHarnessSummary} RuntimeHarnessSummary */

/** @param {unknown} error */
function errorMessage(error) {
  if (error && typeof error === "object" && "message" in error && error.message) {
    return String(error.message);
  }
  return "Invalid model settings.";
}

/**
 * @param {RunStreamRequestContext} context
 * @param {PrepareRunOptions} [options]
 * @returns {PreparedRunRequest | null}
 */
export function prepareRunStreamRequest(context, options = {}) {
  const { elements } = context;
  const isResume = Boolean(options.resumeFromJobId);
  const isRetry = Boolean(options.retryOfJobId);
  const sessionSpec = context.currentSession()?.specification || "";
  const runSpecification = elements.specification?.value.trim() || sessionSpec;
  if (!isResume && !runSpecification.trim()) {
    context.setStatus("Paste or load a specification first.");
    return null;
  }
  let runtimeId = "";
  try {
    if (isResume) {
      runtimeId = requiredRecordedRuntimeHarnessId(options.resumeRunRecord, "resume this run");
    } else if (isRetry) {
      runtimeId = requiredRecordedRuntimeHarnessId(options.retryRunRecord, "retry this run");
    } else {
      const configurationError = runtimeConfigurationError();
      if (configurationError) {
        context.setStatus(configurationError);
        return null;
      }
      runtimeId = elements.runtimeHarnessSelect?.value?.trim() || "";
      if (!runtimeId) {
        context.setStatus("No runtime harness is selected by the application configuration.");
        return null;
      }
    }
  } catch (error) {
    context.setStatus(errorMessage(error));
    return null;
  }
  if (!isResume && !canRunSelectedRuntime()) {
    /** @type {RuntimeHarnessSummary | null | undefined} */
    const selected = selectedRuntimeHarnessSummary();
    context.setStatus(`${selected?.name || runtimeId} is not available to the browser runner.`);
    return null;
  }

  const preserveTraceUntilStart = isResume;
  if (preserveTraceUntilStart) {
    if (elements.jobInfo) elements.jobInfo.textContent = "Preparing resumed run; keeping the archived trace until the backend starts.";
    if (elements.runIdBadge) elements.runIdBadge.textContent = "Run ID: starting...";
  } else {
    if (elements.jobInfo) elements.jobInfo.textContent = "";
    if (elements.runIdBadge) elements.runIdBadge.textContent = "Run ID: starting...";
  }

  /** @type {RuntimeHarnessSummary | null | undefined} */
  const selectedRuntime = isResume
    ? { name: options.resumeRunRecord?.runtime_harness_name || runtimeId }
    : selectedRuntimeHarnessSummary();
  context.setStatus(`Starting ${selectedRuntime?.name || runtimeId}...`);
  /** @type {RuntimeModelBindings | null} */
  let modelBindings = null;
  if (!isResume) {
    try {
      const { modelBinding: recordedBinding } = recordedRuntimeRequestConfig(
        context.currentSession(),
        runtimeId,
      );
      modelBindings = /** @type {RuntimeModelBindings} */ (modelBindingsFromControls(
        runtimeId,
        recordedBinding,
      ));
    } catch (error) {
      context.setStatus(errorMessage(error));
      return null;
    }
  }

  /** @type {CreateRunRequest} */
  let payload;
  if (isResume) {
    payload = {
      resume_from_job_id: /** @type {string} */ (options.resumeFromJobId),
      session_id:
        options.sessionId ||
        context.selectedSessionId() ||
        context.currentSession()?.session_id ||
        options.resumeRunRecord?.session_id ||
        null,
    };
    if (Number.isInteger(options.resumeTraceIndex)) {
      payload.resume_trace_index = /** @type {number} */ (options.resumeTraceIndex);
    }
  } else {
    const { workflowConfig: recordedWorkflow } = recordedRuntimeRequestConfig(
      context.currentSession(),
      runtimeId,
    );
    payload = {
      runtime_harness_id: runtimeId,
      harness_runtime_config: workflowRuntimeConfigFromControls(runtimeId, recordedWorkflow),
      model_bindings: /** @type {RuntimeModelBindings} */ (modelBindings),
      session_id: options.sessionId || context.selectedSessionId() || null,
      specification: runSpecification,
    };
    if (selectedRuntime?.definition_revision) {
      payload.harness_definition_revision = selectedRuntime.definition_revision;
    }
  }
  if (!isResume && options.retryOfJobId) {
    payload.retry_of_job_id = options.retryOfJobId;
  }
  return {
    isResume,
    payload,
    preserveTraceUntilStart,
    runtimeId,
  };
}
