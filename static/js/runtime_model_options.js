import { els } from "./dom.js";
import { getAppConfig } from "./runtime_state.js";
import {
  defaultModelBindingForHarness,
  modelBindingsForHarness,
} from "./runtime_config_selection.js";
import { providerModelCatalog } from "./provider_model_catalog.js";

const CUSTOM_MODEL_VALUE = "__custom__";

function optionValue(option) {
  if (typeof option === "string") return option;
  if (!option || typeof option !== "object") return "";
  return String(option.id || option.model || option.value || option.name || "").trim();
}

function stripRepeatedModelIdSuffix(label, value) {
  let result = String(label || "").trim();
  const suffix = `(${value})`;
  while (result.toLowerCase().endsWith(suffix.toLowerCase())) {
    result = result.slice(0, -suffix.length).trimEnd();
  }
  return result === value ? "" : result;
}

function optionPresentation(option, value) {
  if (!option || typeof option !== "object") return { text: value, priority: 0 };
  const label = String(option.display_name || option.label || option.name || "").trim();
  const friendlyName = stripRepeatedModelIdSuffix(label, value);
  const badges = [];
  if (option.endpoint_available === false) badges.push("not available");
  if (option.stale) badges.push("stale");
  if (option.catalog_known === false) badges.push("custom");
  const identity = friendlyName ? `${friendlyName} (${value})` : value;
  return {
    text: [identity, badges.length ? badges.join(", ") : ""].filter(Boolean).join(" · "),
    priority: (friendlyName ? 2 : 0) + (badges.length ? 1 : 0),
  };
}

function appendModelOption(list, value, presentation = null) {
  const model = String(value || "").trim();
  if (!model) return;
  const candidate = presentation || { text: model, priority: 0 };
  const existing = list.get(model);
  if (!existing || candidate.priority > existing.priority) list.set(model, candidate);
}

export function modelOptionsForProvider(providerId = els.providerSelect?.value, runtimeId = els.runtimeHarnessSelect?.value) {
  const config = getAppConfig();
  const provider = config.providers?.[providerId] || {};
  const options = new Map();
  appendModelOption(options, provider.default_model);

  const configuredModels = providerModelCatalog(provider, providerId)?.models || [];
  for (const configured of Array.isArray(configuredModels) ? configuredModels : []) {
    const value = optionValue(configured);
    appendModelOption(options, value, optionPresentation(configured, value));
  }

  if (providerId === "gemini") {
    for (const configured of config.gemini_models || []) {
      const value = optionValue(configured);
      appendModelOption(options, value, optionPresentation(configured, value));
    }
  }

  const harnessBinding = defaultModelBindingForHarness(runtimeId);
  if (!providerId || harnessBinding.provider === providerId) {
    appendModelOption(options, harnessBinding.model);
  }

  const harnessBindings = modelBindingsForHarness(runtimeId);
  for (const binding of Object.values(harnessBindings || {})) {
    if (!binding || typeof binding !== "object") continue;
    if (!providerId || binding.provider === providerId) appendModelOption(options, binding.model);
  }

  return Array.from(options, ([value, presentation]) => ({ value, label: presentation.text }));
}

function setCustomModelVisible(visible) {
  if (els.customModelField) els.customModelField.hidden = !visible;
}

function applyModelSelection(value, options) {
  const selected = String(value || "").trim();
  const predefined = new Set(options.map((option) => option.value));
  if (els.modelInput) els.modelInput.value = selected;
  if (!els.modelSelect) {
    setCustomModelVisible(true);
    return;
  }
  if (selected && predefined.has(selected)) {
    els.modelSelect.value = selected;
    setCustomModelVisible(false);
    return;
  }
  els.modelSelect.value = CUSTOM_MODEL_VALUE;
  setCustomModelVisible(true);
}

export function refreshModelOptions(
  runtimeId = els.runtimeHarnessSelect?.value,
  providerId = els.providerSelect?.value,
  selectedValue = els.modelInput?.value?.trim() || "",
) {
  if (!els.modelSelect) return;
  const options = modelOptionsForProvider(providerId, runtimeId);
  const fallback = selectedValue || options[0]?.value || defaultModelBindingForHarness(runtimeId).model || "";
  els.modelSelect.innerHTML = "";
  for (const model of options) {
    const option = document.createElement("option");
    option.value = model.value;
    option.textContent = model.label || model.value;
    els.modelSelect.append(option);
  }
  const customOption = document.createElement("option");
  customOption.value = CUSTOM_MODEL_VALUE;
  customOption.textContent = "Custom...";
  els.modelSelect.append(customOption);
  applyModelSelection(fallback, options);
}

export function setModelPickerValue(value, runtimeId = els.runtimeHarnessSelect?.value, providerId = els.providerSelect?.value) {
  refreshModelOptions(runtimeId, providerId, value);
}

export function selectedModelIsManual() {
  return Boolean(els.modelSelect && els.modelSelect.value === CUSTOM_MODEL_VALUE);
}

export function restoreManualModelSelection(value) {
  if (els.modelInput) els.modelInput.value = String(value || "").trim();
  if (els.modelSelect) els.modelSelect.value = CUSTOM_MODEL_VALUE;
  setCustomModelVisible(true);
}

export function onModelSelectChanged() {
  if (!els.modelSelect) return;
  if (els.modelSelect.value === CUSTOM_MODEL_VALUE) {
    setCustomModelVisible(true);
    els.modelInput?.focus();
    return;
  }
  if (els.modelInput) els.modelInput.value = els.modelSelect.value;
  setCustomModelVisible(false);
}
