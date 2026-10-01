import { fetchJson } from "./api.js";
import { els } from "./dom.js";
import { clone } from "./format.js";
import { workflowRuntimeConfig } from "./runtime_request_config.js";
import {
  getAppConfig,
  getHarnessSummaries,
  runtimeHarness,
  runtimeHarnessSummaryById,
  selectedRuntimeHarnessSummary as selectedRuntimeHarnessSummaryFromState,
} from "./runtime_state.js";

/** @typedef {import('../../frontend/src/transport_contracts.js').RuntimeModelBinding} RuntimeModelBinding */
/** @typedef {import('../../frontend/src/transport_contracts.js').RuntimeModelBindings} RuntimeModelBindings */
/** @typedef {import('../../frontend/src/transport_contracts.js').WorkflowRuntimeConfig} WorkflowRuntimeConfig */

export function selectedRuntimeHarnessSummary() {
  return selectedRuntimeHarnessSummaryFromState(els);
}

export async function fetchHarnessTemplate(id) {
  const payload = await fetchJson(`/api/harnesses/${encodeURIComponent(id)}`);
  return payload.harness || runtimeHarnessSummaryById(id) || { id, name: id, runtime_config: {} };
}

export function runtimeConfigForHarness(runtimeId = els.runtimeHarnessSelect?.value) {
  const summary = getHarnessSummaries().find((harness) => harness.id === runtimeId);
  const currentRuntimeHarness = runtimeHarness();
  const active = currentRuntimeHarness?.id === runtimeId ? currentRuntimeHarness : null;
  return clone(summary?.runtime_config || active?.runtime_config || {});
}

export { workflowRuntimeConfig } from "./runtime_request_config.js";

function setNumberFromControl(config, field, control) {
  if (!control) return;
  const value = Number(control.value);
  if (control.value.trim() && Number.isFinite(value)) config[field] = value;
}

/**
 * @param {string} [runtimeId]
 * @param {WorkflowRuntimeConfig | null} [baseConfig]
 * @returns {WorkflowRuntimeConfig}
 */
export function workflowRuntimeConfigFromControls(
  runtimeId = els.runtimeHarnessSelect?.value,
  baseConfig = null,
) {
  const config = workflowRuntimeConfig(
    baseConfig && typeof baseConfig === "object"
      ? { ...runtimeConfigForHarness(runtimeId), ...baseConfig }
      : runtimeConfigForHarness(runtimeId),
  );
  setNumberFromControl(config, "max_iterations", els.maxIterations);
  setNumberFromControl(config, "batch_retries", els.batchRetries);
  setNumberFromControl(config, "no_progress_iterations", els.noProgress);
  if (els.think) config.think = Boolean(els.think.checked);
  if (els.languageRepair) config.language_repair = Boolean(els.languageRepair.checked);
  if (els.semanticCritic) config.semantic_critic = Boolean(els.semanticCritic.checked);
  if (els.completionCheck) config.completion_check = Boolean(els.completionCheck.checked);
  if (els.inferImplicitIdentifiers) {
    config.infer_implicit_identifiers = Boolean(els.inferImplicitIdentifiers.checked);
  }
  if (els.autoCorrectionSequence) {
    config.auto_correction_sequence = Boolean(els.autoCorrectionSequence.checked);
  }
  if (Object.prototype.hasOwnProperty.call(config, "correction_template_id") && els.correctionTemplateSelect?.value) {
    config.correction_template_id = els.correctionTemplateSelect.value;
  }
  return config;
}

export function modelBindingsForHarness(runtimeId = els.runtimeHarnessSelect?.value) {
  const summary = getHarnessSummaries().find((harness) => harness.id === runtimeId);
  const currentRuntimeHarness = runtimeHarness();
  const active = currentRuntimeHarness?.id === runtimeId ? currentRuntimeHarness : null;
  const bindings = summary?.model_bindings || active?.model_bindings || {};
  return clone(bindings?.default ? bindings : { default: bindings });
}

export function defaultModelBindingForHarness(runtimeId = els.runtimeHarnessSelect?.value) {
  const bindings = modelBindingsForHarness(runtimeId);
  return {
    provider: bindings.default?.provider || "",
    model: bindings.default?.model || "",
    base_url: bindings.default?.base_url || null,
    max_completion_tokens: bindings.default?.max_completion_tokens ?? null,
    temperature: bindings.default?.temperature ?? null,
    top_p: bindings.default?.top_p ?? null,
    timeout_seconds: bindings.default?.timeout_seconds ?? 600,
    reasoning_effort: bindings.default?.reasoning_effort ?? null,
    provider_options: clone(bindings.default?.provider_options || {}),
    model_parameters: clone(bindings.default?.model_parameters || {}),
  };
}

function modelParametersFromControls(providerId) {
  if (providerId !== "nvidia_nim") return null;
  const raw = els.modelParametersInput?.value?.trim() || "";
  if (!raw) return {};
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    throw new Error(`Advanced model parameters must be valid JSON. ${error.message || ""}`.trim());
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("Advanced model parameters must be a JSON object.");
  }
  return parsed;
}

function validateModelBindingForHarness(runtimeId, binding) {
  const summary = getHarnessSummaries().find((harness) => harness.id === runtimeId);
  const providerId = String(binding?.provider || "").trim();
  const modelId = String(binding?.model || "").trim();
  if (!providerId || !modelId) return;
  const supported = Array.isArray(summary?.supported_providers) ? summary.supported_providers : [];
  if (supported.length && !supported.includes(providerId)) {
    throw new Error(`${providerId} is not supported by ${summary?.name || runtimeId}.`);
  }
}

/**
 * @param {string} [runtimeId]
 * @param {RuntimeModelBinding | null} [baseBinding]
 * @returns {RuntimeModelBindings}
 */
export function modelBindingsFromControls(
  runtimeId = els.runtimeHarnessSelect?.value,
  baseBinding = null,
) {
  const fallback = defaultModelBindingForHarness(runtimeId);
  const source = baseBinding && typeof baseBinding === "object" ? clone(baseBinding) : {};
  const binding = {
    ...fallback,
    ...source,
    provider_options: clone(source.provider_options || fallback.provider_options || {}),
    model_parameters: clone(source.model_parameters || fallback.model_parameters || {}),
  };
  const selectedProvider = els.providerSelect?.value || binding.provider;
  if (selectedProvider && selectedProvider !== binding.provider) {
    const descriptor = getAppConfig().providers?.[selectedProvider] || {};
    binding.provider = selectedProvider;
    binding.base_url = descriptor.default_base_url || null;
    binding.model = descriptor.default_model || binding.model;
    binding.reasoning_effort = descriptor.supports_reasoning_effort ? (binding.reasoning_effort || "xhigh") : null;
  }
  if (els.modelInput?.value?.trim()) binding.model = els.modelInput.value.trim();
  if (els.numPredict?.value) binding.max_completion_tokens = Number(els.numPredict.value);
  binding.temperature = els.temperature?.value ? Number(els.temperature.value) : null;
  binding.top_p = els.topP?.value ? Number(els.topP.value) : null;
  binding.timeout_seconds = binding.timeout_seconds || 600;
  const controlledModelParameters = modelParametersFromControls(binding.provider);
  if (controlledModelParameters !== null) {
    binding.model_parameters = controlledModelParameters;
  }
  validateModelBindingForHarness(runtimeId, binding);
  return { default: binding };
}
