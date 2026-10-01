let appConfig = {};
let harnessSummaries = [];
let runtimeHarnessGetter = () => null;
let onCorrectionTemplateDescriptionChanged = () => {};
let onRetryRunControlsChanged = () => {};
let onRuntimeHarnessBadgeChanged = () => {};

export function runtimeConfigurationError() {
  const configuredId = String(appConfig.default_runtime_harness_id || "").trim();
  if (!configuredId) {
    return "Application configuration is missing default_runtime_harness_id.";
  }
  const configuredHarness = harnessSummaries.find((harness) => harness.id === configuredId);
  if (!configuredHarness) {
    return `Configured default runtime harness '${configuredId}' is unavailable.`;
  }
  if (!configuredHarness.runnable) {
    return `Configured default runtime harness '${configuredId}' is not runnable.`;
  }
  return "";
}

export function configureRuntimeControls(options = {}) {
  if (typeof options.getRuntimeHarness === "function") runtimeHarnessGetter = options.getRuntimeHarness;
  if (typeof options.updateCorrectionTemplateDescription === "function") {
    onCorrectionTemplateDescriptionChanged = options.updateCorrectionTemplateDescription;
  }
  if (typeof options.updateRetryRunControls === "function") {
    onRetryRunControlsChanged = options.updateRetryRunControls;
  }
  if (typeof options.updateRuntimeHarnessBadge === "function") {
    onRuntimeHarnessBadgeChanged = options.updateRuntimeHarnessBadge;
  }
}

export function getAppConfig() {
  return appConfig;
}

export function setAppConfig(config = {}) {
  appConfig = config || {};
  return appConfig;
}

export function patchAppConfig(patch = {}) {
  appConfig = { ...appConfig, ...(patch || {}) };
  return appConfig;
}

export function getHarnessSummaries() {
  return harnessSummaries;
}

export function setHarnessSummaries(summaries = []) {
  harnessSummaries = Array.isArray(summaries) ? summaries : [];
  return harnessSummaries;
}

export function runtimeHarness() {
  return runtimeHarnessGetter();
}

export function notifyCorrectionTemplateDescriptionChanged() {
  onCorrectionTemplateDescriptionChanged();
}

export function notifyRetryRunControlsChanged() {
  onRetryRunControlsChanged();
}

export function notifyRuntimeHarnessBadgeChanged() {
  onRuntimeHarnessBadgeChanged();
}

export function providerName() {
  const selectedId = document.querySelector("#providerSelect")?.value || appConfig.default_provider || appConfig.provider || "gemini";
  return appConfig.providers?.[selectedId]?.label || selectedId;
}

export function selectedRuntimeHarnessSummary(elements = {}) {
  const selectedId = elements.runtimeHarnessSelect?.value || appConfig.default_runtime_harness_id || "";
  return harnessSummaries.find((harness) => harness.id === selectedId) || null;
}

export function runtimeHarnessSummaryById(runtimeId) {
  return harnessSummaries.find((harness) => harness.id === runtimeId) || null;
}
