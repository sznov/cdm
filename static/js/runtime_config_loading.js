import { fetchJson } from "./api.js";
import { els } from "./dom.js";
import { applyRuntimeHarnessConfigToControls } from "./runtime_harness_form.js";
import {
  getAppConfig,
  runtimeConfigurationError,
  setAppConfig,
  setHarnessSummaries,
} from "./runtime_state.js";
import { updateRuntimeRunControls } from "./runtime_run_controls.js";
import {
  refreshModelOptions,
  restoreManualModelSelection,
  selectedModelIsManual,
} from "./runtime_model_options.js";
import {
  describeProviderModelCatalog,
  normalizeProviderModelCatalog,
  providerModelCatalog,
} from "./provider_model_catalog.js";
import { renderStartupRecoveryNotice } from "./startup_recovery_notice.js";

/** @typedef {import('../../frontend/src/transport_contracts.js').ApplicationRuntimeConfig} ApplicationRuntimeConfig */

const REFRESHABLE_PROVIDERS = new Set(["gemini", "nvidia_nim"]);
const providerRefreshRequests = new Map();
const ENRICHMENT_POLL_INTERVAL_MS = 1000;
const ENRICHMENT_POLL_MAX_MS = 60_000;
let configLoadSequence = 0;
let enrichmentPollSequence = 0;
let enrichmentPoll = null;

function providerRefreshState(providerId, config = getAppConfig()) {
  return config?.providers?.[providerId]?.model_refresh || config?.providers?.[providerId]?.catalog_refresh || {};
}

function enrichmentIsRunning(state) {
  return state?.enrichment?.status === "running";
}

export function stopProviderModelCatalogPolling() {
  enrichmentPollSequence += 1;
  if (enrichmentPoll?.timer) clearTimeout(enrichmentPoll.timer);
  enrichmentPoll = null;
}

function pollingStillApplies(providerId) {
  return providerId === "nvidia_nim" &&
    Boolean(els.newSessionModal?.open) &&
    els.providerSelect?.value === providerId;
}

function applyProviderCatalogResponse(providerId, payload) {
  const catalog = normalizeProviderModelCatalog(payload, providerId);
  const config = getAppConfig();
  const provider = config?.providers?.[providerId];
  if (!catalog || !provider) return null;
  const selectedProviderId = els.providerSelect?.value || "";
  const selectedModel = els.modelInput?.value?.trim() || els.modelSelect?.value || "";
  const manual = selectedProviderId === providerId && selectedModelIsManual();
  provider.model_catalog = catalog;
  provider.models = catalog.models;
  provider.model_refresh = payload?.state || provider.model_refresh || {};
  if (providerId === "nvidia_nim") provider.catalog_refresh = { ...provider.model_refresh };
  if (selectedProviderId === providerId) {
    refreshModelOptions(undefined, providerId, selectedModel);
    if (manual) restoreManualModelSelection(selectedModel);
    updateProviderModelRefreshUi(providerId);
    updateRuntimeRunControls();
  }
  return provider.model_refresh;
}

function ensureEnrichmentPolling(providerId, state) {
  if (!pollingStillApplies(providerId) || !enrichmentIsRunning(state)) {
    stopProviderModelCatalogPolling();
    return;
  }
  if (enrichmentPoll?.providerId === providerId) return;
  stopProviderModelCatalogPolling();
  const sequence = ++enrichmentPollSequence;
  enrichmentPoll = {
    providerId,
    startedAt: Date.now(),
    timer: null,
  };

  const schedule = () => {
    if (!enrichmentPoll || enrichmentPollSequence !== sequence) return;
    enrichmentPoll.timer = setTimeout(async () => {
      if (!enrichmentPoll || enrichmentPollSequence !== sequence) return;
      if (!pollingStillApplies(providerId) || Date.now() - enrichmentPoll.startedAt >= ENRICHMENT_POLL_MAX_MS) {
        stopProviderModelCatalogPolling();
        return;
      }
      try {
        const payload = await fetchJson(`/api/providers/${encodeURIComponent(providerId)}/models`);
        if (enrichmentPollSequence !== sequence) return;
        const nextState = applyProviderCatalogResponse(providerId, payload);
        if (!enrichmentIsRunning(nextState)) {
          stopProviderModelCatalogPolling();
          return;
        }
      } catch {
        // A transient local read failure does not invalidate the live list.
      }
      schedule();
    }, ENRICHMENT_POLL_INTERVAL_MS);
  };
  schedule();
}

export function updateProviderModelRefreshUi(providerId = els.providerSelect?.value) {
  const selectedProviderId = els.providerSelect?.value || "";
  if (selectedProviderId && providerId && providerId !== selectedProviderId) return;
  providerId = selectedProviderId || providerId;
  const supported = REFRESHABLE_PROVIDERS.has(providerId || "");
  const provider = getAppConfig()?.providers?.[providerId] || {};
  const catalog = providerModelCatalog(provider, providerId);
  const state = providerRefreshState(providerId);
  const running = providerRefreshRequests.has(providerId) || state.status === "running";
  if (els.modelRefreshButton) {
    els.modelRefreshButton.hidden = !supported;
    els.modelRefreshButton.disabled = !supported || running;
    els.modelRefreshButton.classList.toggle("is-running", running);
  }
  if (els.modelRefreshStatus) {
    const selectedModel = els.modelInput?.value?.trim() || els.modelSelect?.value || "";
    const status = describeProviderModelCatalog({
      catalog,
      providerLabel: provider.label || providerId,
      refreshState: state,
      running,
      selectedModel,
      manual: selectedModelIsManual(),
    });
    els.modelRefreshStatus.hidden = (!supported && !catalog) || !status.text;
    els.modelRefreshStatus.textContent = status.text;
    els.modelRefreshStatus.title = status.detail;
    els.modelRefreshStatus.setAttribute("aria-label", status.detail);
    els.modelRefreshStatus.classList.toggle("is-error", Boolean(status.error));
    els.modelRefreshStatus.classList.toggle("is-warning", Boolean(status.warning));
    els.modelRefreshStatus.classList.toggle("is-stale", Boolean(status.stale));
    els.modelRefreshStatus.classList.toggle("is-unverified", Boolean(status.unverified));
    els.modelRefreshStatus.classList.toggle("is-manual", status.modelMembership === "manual" || status.modelMembership === "unlisted");
    els.modelRefreshStatus.dataset.catalogSource = status.source;
    els.modelRefreshStatus.dataset.catalogOrigin = status.origin;
    els.modelRefreshStatus.dataset.catalogStale = String(status.stale);
    els.modelRefreshStatus.dataset.catalogUnverified = String(status.unverified);
    els.modelRefreshStatus.dataset.modelMembership = status.modelMembership;
  }
  ensureEnrichmentPolling(providerId, state);
}

export async function loadConfig({ preserveProvider = false, preserveModel = false } = {}) {
  const loadSequence = ++configLoadSequence;
  const config = /** @type {ApplicationRuntimeConfig} */ (await fetchJson("/api/config"));
  if (loadSequence !== configLoadSequence) return getAppConfig();
  // Read the selection only after the response arrives. A user may choose or
  // type a model while discovery is in flight; an earlier snapshot must never
  // overwrite that newer explicit choice.
  const previousProvider = preserveProvider ? els.providerSelect?.value : "";
  const previousModel = preserveModel ? (els.modelInput?.value?.trim() || els.modelSelect?.value || "") : "";
  setAppConfig(config || {});
  renderStartupRecoveryNotice(config?.startup_recovery);
  if (els.providerSelect) {
    els.providerSelect.innerHTML = "";
    for (const [providerId, provider] of Object.entries(config.providers || {})) {
      const option = document.createElement("option");
      option.value = providerId;
      option.textContent = provider.label || providerId;
      els.providerSelect.append(option);
    }
    els.providerSelect.value =
      previousProvider && config.providers?.[previousProvider]
        ? previousProvider
        : config.default_provider || config.provider || "gemini";
    refreshModelOptions(undefined, els.providerSelect.value, previousModel);
    updateProviderModelRefreshUi(els.providerSelect.value);
  }
  if (els.maxIterations) els.maxIterations.value = config.max_iterations;
  if (els.batchRetries) els.batchRetries.value = config.batch_retries;
  if (els.noProgress) els.noProgress.value = config.no_progress_iterations;
  if (els.numPredict) els.numPredict.value = config.num_predict;
  if (els.think) els.think.checked = Boolean(config.think);
  if (els.languageRepair) els.languageRepair.checked = Boolean(config.language_repair);
  if (els.semanticCritic) els.semanticCritic.checked = Boolean(config.semantic_critic);
  if (els.completionCheck) els.completionCheck.checked = Boolean(config.completion_check);
  if (els.inferImplicitIdentifiers) els.inferImplicitIdentifiers.checked = Boolean(config.infer_implicit_identifiers);
}

export function refreshProviderModels(providerId = els.providerSelect?.value, { force = false } = {}) {
  if (!REFRESHABLE_PROVIDERS.has(providerId || "")) return Promise.resolve(null);
  if (providerRefreshRequests.has(providerId)) return providerRefreshRequests.get(providerId);
  updateProviderModelRefreshUi(providerId);
  const request = fetchJson(`/api/providers/${encodeURIComponent(providerId)}/models/refresh?force=${force ? "true" : "false"}`, {
    method: "POST",
  })
    .then((payload) => {
      applyProviderCatalogResponse(providerId, payload);
      return payload;
    })
    .catch((error) => {
      const config = getAppConfig();
      const provider = config.providers?.[providerId];
      if (provider) {
        provider.model_refresh = {
          ...(provider.model_refresh || provider.catalog_refresh || {}),
          status: "failed",
          last_error: error?.message || String(error),
        };
      }
      updateProviderModelRefreshUi(providerId);
      throw error;
    })
    .finally(() => {
      providerRefreshRequests.delete(providerId);
      updateProviderModelRefreshUi(providerId);
      updateRuntimeRunControls();
    });
  providerRefreshRequests.set(providerId, request);
  updateProviderModelRefreshUi(providerId);
  return request;
}

export function triggerStartupProviderModelRefreshes() {
  for (const providerId of REFRESHABLE_PROVIDERS) {
    refreshProviderModels(providerId, { force: false }).catch(() => {
      // Startup refresh is opportunistic; cached config remains usable.
    });
  }
}

export function refreshSelectedProviderModels({ force = false } = {}) {
  const providerId = els.providerSelect?.value || "";
  return refreshProviderModels(providerId, { force });
}

export async function loadHarnesses() {
  const payload = await fetchJson("/api/harnesses");
  const summaries = setHarnessSummaries(payload.harnesses || []);
  if (els.runtimeHarnessSelect) els.runtimeHarnessSelect.innerHTML = "";
  for (const harness of summaries) {
    if (els.runtimeHarnessSelect) {
      const runtimeOption = document.createElement("option");
      runtimeOption.value = harness.id;
      runtimeOption.textContent = harness.runnable ? harness.name : `${harness.name} (view only)`;
      runtimeOption.disabled = !harness.runnable;
      els.runtimeHarnessSelect.append(runtimeOption);
    }
  }
  if (els.runtimeHarnessSelect) {
    const configuredDefault = summaries.find((harness) => harness.id === getAppConfig().default_runtime_harness_id && harness.runnable);
    els.runtimeHarnessSelect.value = configuredDefault?.id || "";
    els.runtimeHarnessSelect.setAttribute("aria-invalid", runtimeConfigurationError() ? "true" : "false");
  }
  applyRuntimeHarnessConfigToControls();
  refreshModelOptions();
  updateProviderModelRefreshUi();
  updateRuntimeRunControls();
}
