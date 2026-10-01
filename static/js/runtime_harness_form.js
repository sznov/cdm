import { els } from "./dom.js";
import {
  getAppConfig,
  notifyCorrectionTemplateDescriptionChanged,
  providerName,
} from "./runtime_state.js";
import {
  defaultModelBindingForHarness,
  runtimeConfigForHarness,
} from "./runtime_config_selection.js";
import { setModelPickerValue } from "./runtime_model_options.js";

function formatOptionalConfigValue(value, fallback = "default") {
  return value == null || value === "" ? fallback : String(value);
}

export function updateModelParametersControls(binding = defaultModelBindingForHarness()) {
  const providerId = els.providerSelect?.value || binding.provider;
  const visible = providerId === "nvidia_nim";
  if (els.modelParametersField) els.modelParametersField.hidden = !visible;
  if (!visible) return;
  const parameters = binding.model_parameters && typeof binding.model_parameters === "object"
    ? binding.model_parameters
    : {};
  if (els.modelParametersInput && !els.modelParametersInput.value.trim()) {
    els.modelParametersInput.value = Object.keys(parameters).length ? JSON.stringify(parameters, null, 2) : "";
  }
}

export function applyRuntimeHarnessConfigToControls(runtimeId = els.runtimeHarnessSelect?.value, options = {}) {
  const config = runtimeConfigForHarness(runtimeId);
  const binding = defaultModelBindingForHarness(runtimeId);
  if (!options.preserveModelBinding) {
    if (els.providerSelect) els.providerSelect.value = binding.provider || getAppConfig().default_provider || "gemini";
    setModelPickerValue(binding.model || getAppConfig().default_model || "", runtimeId, els.providerSelect?.value);
  } else {
    setModelPickerValue(els.modelInput?.value || binding.model || getAppConfig().default_model || "", runtimeId, els.providerSelect?.value);
  }
  if (!options.preserveModelBinding && els.modelParametersInput) {
    els.modelParametersInput.value = binding.model_parameters && Object.keys(binding.model_parameters).length
      ? JSON.stringify(binding.model_parameters, null, 2)
      : "";
  }
  updateModelParametersControls(binding);
  if (config.max_iterations != null && els.maxIterations) els.maxIterations.value = config.max_iterations;
  if (config.batch_retries != null && els.batchRetries) els.batchRetries.value = config.batch_retries;
  if (config.no_progress_iterations != null && els.noProgress) els.noProgress.value = config.no_progress_iterations;
  if (els.numPredict) els.numPredict.value = binding.max_completion_tokens ?? "";
  if (els.temperature) els.temperature.value = binding.temperature ?? "";
  if (els.topP) els.topP.value = binding.top_p ?? "";
  if (els.think) els.think.checked = Boolean(config.think);
  if (els.languageRepair) els.languageRepair.checked = config.language_repair !== false;
  if (els.semanticCritic) els.semanticCritic.checked = config.semantic_critic !== false;
  if (els.completionCheck) els.completionCheck.checked = config.completion_check !== false;
  if (els.inferImplicitIdentifiers) els.inferImplicitIdentifiers.checked = config.infer_implicit_identifiers !== false;
  if (els.autoCorrectionSequence) els.autoCorrectionSequence.checked = Boolean(config.auto_correction_sequence);
  if (els.correctionTemplateSelect && config.correction_template_id) {
    els.correctionTemplateSelect.value = config.correction_template_id;
    notifyCorrectionTemplateDescriptionChanged();
  }
}

export function renderHarnessConfigPreview(runtimeId = els.runtimeHarnessSelect?.value) {
  if (!els.harnessConfigPreview) return;
  if (!runtimeId) {
    els.harnessConfigPreview.hidden = true;
    els.harnessConfigPreview.textContent = "";
    return;
  }
  const config = runtimeConfigForHarness(runtimeId);
  const binding = defaultModelBindingForHarness(runtimeId);
  const model = els.modelInput?.value?.trim() || binding.model || getAppConfig().default_model || "model?";
  const toggles = [
    config.language_repair !== false ? "language repair" : null,
    config.semantic_critic !== false ? "semantic critic" : null,
    config.completion_check !== false ? "completion check" : null,
    config.infer_implicit_identifiers !== false ? "identifier context" : null,
    config.think ? "thinking flag" : null,
  ].filter(Boolean);
  const details = [
    `${providerName()} · ${model}`,
    `retries ${formatOptionalConfigValue(config.batch_retries)}`,
    `tokens ${formatOptionalConfigValue(binding.max_completion_tokens)}`,
    toggles.length ? toggles.join(", ") : "no optional passes",
  ];
  els.harnessConfigPreview.textContent = `Harness config: ${details.join(" · ")}`;
  els.harnessConfigPreview.hidden = false;
}
