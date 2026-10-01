import { applyRuntimeHarnessConfigToControls, updateModelParametersControls } from "./runtime_harness_form.js";
import { updateProviderModelRefreshUi } from "./runtime_config_loading.js";
import { getAppConfig, notifyRuntimeHarnessBadgeChanged } from "./runtime_state.js";
import { updateRuntimeRunControls } from "./runtime_run_controls.js";
import { onModelSelectChanged as syncModelSelectChanged, setModelPickerValue } from "./runtime_model_options.js";

export function onRuntimeHarnessChanged() {
  applyRuntimeHarnessConfigToControls();
  updateRuntimeRunControls();
  notifyRuntimeHarnessBadgeChanged();
}

export function onProviderChanged() {
  const providerId = document.querySelector("#providerSelect")?.value || "";
  const defaultModel = getAppConfig().providers?.[providerId]?.default_model;
  setModelPickerValue(defaultModel || "", undefined, providerId);
  updateModelParametersControls();
  updateProviderModelRefreshUi(providerId);
  updateRuntimeRunControls();
  notifyRuntimeHarnessBadgeChanged();
}

export function onModelSelectChanged() {
  syncModelSelectChanged();
  updateModelParametersControls();
  updateProviderModelRefreshUi();
  updateRuntimeRunControls();
  notifyRuntimeHarnessBadgeChanged();
}

export function onModelBindingChanged() {
  updateProviderModelRefreshUi();
  updateRuntimeRunControls();
  notifyRuntimeHarnessBadgeChanged();
}
