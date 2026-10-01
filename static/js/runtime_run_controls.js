import { els } from "./dom.js";
import { renderHarnessConfigPreview } from "./runtime_harness_form.js";
import { selectedRuntimeHarnessSummary } from "./runtime_config_selection.js";
import {
  getAppConfig,
  notifyRetryRunControlsChanged,
  runtimeConfigurationError,
} from "./runtime_state.js";

function selectedProviderConfigurationError() {
  const providerId = els.providerSelect?.value || "";
  const provider = getAppConfig()?.providers?.[providerId];
  const refresh = provider?.model_refresh || provider?.catalog_refresh || {};
  return String(refresh.configuration_error || "").trim();
}

export function canRunSelectedRuntime() {
  return Boolean(
    selectedRuntimeHarnessSummary()?.runnable &&
    !runtimeConfigurationError() &&
    !selectedProviderConfigurationError()
  );
}

export function newSessionSpecificationHasText() {
  return Boolean(els.specification?.value.trim());
}

export function updateRuntimeRunControls() {
  const selected = selectedRuntimeHarnessSummary();
  const configurationError = (
    runtimeConfigurationError() ||
    selectedProviderConfigurationError()
  );
  const runnable = !configurationError && Boolean(selected?.runnable);
  const hasSpecification = newSessionSpecificationHasText();
  if (els.runButton) {
    els.runButton.disabled = !runnable || !hasSpecification;
    els.runButton.textContent = runnable ? "Start" : configurationError ? "Configuration Error" : "Runtime Not Runnable";
    els.runButton.title = configurationError
      ? configurationError
      : !runnable
      ? "Selected runtime is not runnable."
      : !hasSpecification
      ? "Paste a specification first."
      : "Start modeling session.";
  }
  if (els.runtimeHarnessHint) {
    const note = selected?.runtime_note || "Choose the backend harness that the Run button will execute.";
    els.runtimeHarnessHint.textContent = configurationError
      ? configurationError
      : selected
      ? `${selected.name}: ${note}`
      : "No runtime harness selected.";
    els.runtimeHarnessHint.hidden = !configurationError && !selected;
    els.runtimeHarnessHint.classList.toggle("warning", Boolean(configurationError || (selected && !runnable)));
  }
  renderHarnessConfigPreview();
  notifyRetryRunControlsChanged();
}
