import { setModelPickerValue } from "./runtime_model_options.js";

export async function applySessionToControls(context, session) {
  if (!session) return;
  const { elements } = context;
  if (elements.specification) elements.specification.value = session.specification || "";
  if (elements.runtimeHarnessSelect && session.runtime_harness_id) {
    elements.runtimeHarnessSelect.value = session.runtime_harness_id;
    context.onRuntimeHarnessChanged();
  }
  const binding = session.model_bindings?.default;
  if (binding?.provider && elements.providerSelect) elements.providerSelect.value = binding.provider;
  setModelPickerValue(binding?.model || "", session.runtime_harness_id || elements.runtimeHarnessSelect?.value, elements.providerSelect?.value);
  if (elements.numPredict) elements.numPredict.value = binding?.max_completion_tokens ?? "";
  if (elements.temperature) elements.temperature.value = binding?.temperature ?? "";
  if (elements.topP) elements.topP.value = binding?.top_p ?? "";
  if (elements.modelParametersInput) {
    const parameters = binding?.model_parameters;
    elements.modelParametersInput.value = parameters && Object.keys(parameters).length
      ? JSON.stringify(parameters, null, 2)
      : "";
  }
  const workflow = session.harness_runtime_config || {};
  if (workflow.max_iterations != null && elements.maxIterations) elements.maxIterations.value = workflow.max_iterations;
  if (workflow.batch_retries != null && elements.batchRetries) elements.batchRetries.value = workflow.batch_retries;
  if (workflow.no_progress_iterations != null && elements.noProgress) elements.noProgress.value = workflow.no_progress_iterations;
  if (workflow.think != null && elements.think) elements.think.checked = Boolean(workflow.think);
  if (workflow.language_repair != null && elements.languageRepair) {
    elements.languageRepair.checked = Boolean(workflow.language_repair);
  }
  if (workflow.semantic_critic != null && elements.semanticCritic) {
    elements.semanticCritic.checked = Boolean(workflow.semantic_critic);
  }
  if (workflow.completion_check != null && elements.completionCheck) {
    elements.completionCheck.checked = Boolean(workflow.completion_check);
  }
  if (workflow.infer_implicit_identifiers != null && elements.inferImplicitIdentifiers) {
    elements.inferImplicitIdentifiers.checked = Boolean(workflow.infer_implicit_identifiers);
  }
  if (workflow.auto_correction_sequence != null && elements.autoCorrectionSequence) {
    elements.autoCorrectionSequence.checked = Boolean(workflow.auto_correction_sequence);
  }
  if (
    Object.prototype.hasOwnProperty.call(workflow, "correction_template_id") &&
    elements.correctionTemplateSelect
  ) {
    elements.correctionTemplateSelect.value = workflow.correction_template_id ?? "";
  }
  context.renderHarnessConfigPreview(session.runtime_harness_id);
}
