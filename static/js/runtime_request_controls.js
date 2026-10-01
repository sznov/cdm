import { els } from "./dom.js";
import { onRuntimeHarnessChanged } from "./runtime_harness_controls.js";
import { setModelPickerValue } from "./runtime_model_options.js";
import { notifyCorrectionTemplateDescriptionChanged } from "./runtime_state.js";

export function applyRunRequestToControls(run = {}) {
  const effectiveSpec = run?.effective_harness_run_spec || {};
  const runtimeHarnessId = run?.runtime_harness_id || effectiveSpec.harness_id || "";
  const config = effectiveSpec.effective_config || {};
  if (runtimeHarnessId && els.runtimeHarnessSelect) {
    els.runtimeHarnessSelect.value = runtimeHarnessId;
    onRuntimeHarnessChanged();
  }
  const binding = run?.model_bindings?.default || effectiveSpec.model_bindings?.default;
  if (binding?.provider && els.providerSelect) els.providerSelect.value = binding.provider;
  setModelPickerValue(binding?.model || "", runtimeHarnessId || els.runtimeHarnessSelect?.value, els.providerSelect?.value);
  if (config.max_iterations != null && els.maxIterations) els.maxIterations.value = config.max_iterations;
  if (config.batch_retries != null && els.batchRetries) els.batchRetries.value = config.batch_retries;
  if (config.no_progress_iterations != null && els.noProgress) els.noProgress.value = config.no_progress_iterations;
  if (binding?.max_completion_tokens != null && els.numPredict) {
    els.numPredict.value = binding.max_completion_tokens;
  }
  if (els.modelParametersInput) {
    const parameters = binding?.model_parameters;
    els.modelParametersInput.value = parameters && Object.keys(parameters).length
      ? JSON.stringify(parameters, null, 2)
      : "";
  }
  if (els.temperature) els.temperature.value = binding?.temperature ?? "";
  if (els.topP) els.topP.value = binding?.top_p ?? "";
  if (config.think != null && els.think) els.think.checked = Boolean(config.think);
  if (config.language_repair != null && els.languageRepair) {
    els.languageRepair.checked = Boolean(config.language_repair);
  }
  if (config.semantic_critic != null && els.semanticCritic) {
    els.semanticCritic.checked = Boolean(config.semantic_critic);
  }
  if (config.completion_check != null && els.completionCheck) {
    els.completionCheck.checked = Boolean(config.completion_check);
  }
  if (config.infer_implicit_identifiers != null && els.inferImplicitIdentifiers) {
    els.inferImplicitIdentifiers.checked = Boolean(config.infer_implicit_identifiers);
  }
  if (config.auto_correction_sequence != null && els.autoCorrectionSequence) {
    els.autoCorrectionSequence.checked = Boolean(config.auto_correction_sequence);
  }
  if (config.correction_template_id && els.correctionTemplateSelect) {
    els.correctionTemplateSelect.value = config.correction_template_id;
    notifyCorrectionTemplateDescriptionChanged();
  }
}
