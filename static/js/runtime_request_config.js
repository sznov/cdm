// @ts-check

import { clone } from "./format_misc.js";

/** @typedef {import('../../frontend/src/transport_contracts.js').WorkflowRuntimeConfig} WorkflowRuntimeConfig */
/** @typedef {import('../../frontend/src/transport_contracts.js').RuntimeModelBinding} RuntimeModelBinding */
/** @typedef {import('../../frontend/src/transport_contracts.js').RuntimeSessionRequestProjection} RuntimeSessionRequestProjection */
/** @typedef {import('../../frontend/src/transport_contracts.js').RecordedRunProjection} RecordedRunProjection */

/** @type {readonly (keyof WorkflowRuntimeConfig)[]} */
const WORKFLOW_RUNTIME_CONFIG_FIELDS = Object.freeze([
  "max_iterations",
  "batch_retries",
  "no_progress_iterations",
  "think",
  "language_repair",
  "semantic_critic",
  "completion_check",
  "infer_implicit_identifiers",
  "auto_correction_sequence",
  "correction_template_id",
  "max_attempts",
  "direct_microop_judge",
  "max_correction_operations",
  "prompt_profile",
]);

/**
 * @param {unknown} config
 * @returns {WorkflowRuntimeConfig}
 */
export function workflowRuntimeConfig(config = {}) {
  const source = config && typeof config === "object" && !Array.isArray(config)
    ? /** @type {Record<string, unknown>} */ (config)
    : {};
  /** @type {Record<string, unknown>} */
  const result = {};
  for (const field of WORKFLOW_RUNTIME_CONFIG_FIELDS) {
    if (Object.prototype.hasOwnProperty.call(source, field) && source[field] !== undefined) {
      result[field] = clone(source[field]);
    }
  }
  return /** @type {WorkflowRuntimeConfig} */ (result);
}

/**
 * Return a detached request projection only when the selected session was
 * recorded with the harness that is about to run. Hidden provider and workflow
 * settings therefore follow the session rather than whichever session was
 * previously rendered into the controls.
 *
 * @param {RuntimeSessionRequestProjection | null | undefined} session
 * @param {string} runtimeId
 * @returns {{modelBinding: RuntimeModelBinding | null, workflowConfig: WorkflowRuntimeConfig | null}}
 */
export function recordedRuntimeRequestConfig(session, runtimeId) {
  if (!session || session.runtime_harness_id !== runtimeId) {
    return { modelBinding: null, workflowConfig: null };
  }
  const binding = session.model_bindings?.default;
  return {
    modelBinding: binding ? clone(binding) : null,
    workflowConfig: session.harness_runtime_config
      ? workflowRuntimeConfig(session.harness_runtime_config)
      : null,
  };
}

/**
 * Archived actions must use the protocol recorded by the run. Falling back to
 * the current application default can silently execute a different scientific
 * protocol after a catalog or configuration change.
 *
 * @param {RecordedRunProjection | null | undefined} run
 * @param {string} [action]
 * @returns {string}
 */
export function requiredRecordedRuntimeHarnessId(run, action = "use this archived run") {
  const runtimeId = String(
    run?.runtime_harness_id || run?.effective_harness_run_spec?.harness_id || "",
  ).trim();
  if (!runtimeId) {
    throw new Error(`Cannot ${action} because its recorded runtime harness identity is unavailable.`);
  }
  return runtimeId;
}
