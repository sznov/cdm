// @ts-check

/** @typedef {import("../../frontend/src/provider_catalog_contracts.js").ProviderCatalogOrigin} ProviderCatalogOrigin */
/** @typedef {import("../../frontend/src/provider_catalog_contracts.js").ProviderCatalogSource} ProviderCatalogSource */
/** @typedef {import("../../frontend/src/provider_catalog_contracts.js").ProviderModelCatalogEnvelope} ProviderModelCatalogEnvelope */
/** @typedef {import("../../frontend/src/provider_catalog_contracts.js").ProviderModelCatalogStatus} ProviderModelCatalogStatus */
/** @typedef {import("../../frontend/src/provider_catalog_contracts.js").ProviderModelCatalogStatusOptions} ProviderModelCatalogStatusOptions */
/** @typedef {import("../../frontend/src/provider_catalog_contracts.js").ProviderModelDescriptor} ProviderModelDescriptor */
/** @typedef {import("../../frontend/src/provider_catalog_contracts.js").ProviderModelOption} ProviderModelOption */
/** @typedef {import("../../frontend/src/run_contracts.js").JsonObject} JsonObject */

const CATALOG_SOURCES = new Set(["live", "persisted", "bundled"]);
const CATALOG_ORIGINS = new Set(["live", "bundled"]);

/** @param {unknown} value */
function isRecord(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

/**
 * @param {unknown} value
 * @returns {Record<string, unknown>}
 */
function asRecord(value) {
  return isRecord(value) ? /** @type {Record<string, unknown>} */ (value) : {};
}

/**
 * @param {unknown} value
 * @returns {unknown}
 */
function detachJsonValue(value) {
  if (Array.isArray(value)) return value.map(detachJsonValue);
  if (!isRecord(value)) return value;
  return Object.fromEntries(
    Object.entries(asRecord(value)).map(([key, nested]) => [key, detachJsonValue(nested)]),
  );
}

/**
 * @param {unknown} value
 * @returns {ProviderCatalogSource}
 */
function catalogSource(value) {
  const source = String(value || "").trim().toLowerCase();
  return CATALOG_SOURCES.has(source) ? /** @type {ProviderCatalogSource} */ (source) : "unknown";
}

/**
 * @param {unknown} value
 * @returns {ProviderCatalogOrigin}
 */
function catalogOrigin(value) {
  const origin = String(value || "").trim().toLowerCase();
  return CATALOG_ORIGINS.has(origin) ? /** @type {ProviderCatalogOrigin} */ (origin) : "unknown";
}

/**
 * Return a detached catalog envelope so UI code cannot mutate the API payload.
 *
 * @param {unknown} value
 * @param {string} [expectedProviderId]
 * @returns {ProviderModelCatalogEnvelope | null}
 */
export function normalizeProviderModelCatalog(value, expectedProviderId = "") {
  if (!isRecord(value)) return null;
  const record = asRecord(value);
  if (!Array.isArray(record.models)) return null;
  if ("schema_version" in record && record.schema_version !== 1) return null;
  const providerId = String(record.provider_id || expectedProviderId || "").trim();
  if (expectedProviderId && providerId && providerId !== expectedProviderId) return null;
  const provenance = asRecord(record.provenance);
  const schemaVersion = Number.isInteger(record.schema_version) ? Number(record.schema_version) : null;
  const warning = String(record.warning || "").trim() || null;
  const retrievedAt = String(record.retrieved_at_utc || "").trim() || null;
  /** @type {ProviderModelOption[]} */
  const models = record.models
    .filter((model) => typeof model === "string" || isRecord(model))
    .map((model) => typeof model === "string"
      ? model
      : /** @type {ProviderModelDescriptor} */ (detachJsonValue(model)));
  const source = catalogSource(record.source);
  return {
    schema_version: schemaVersion,
    provider_id: providerId || expectedProviderId,
    source,
    origin: catalogOrigin(record.origin),
    retrieved_at_utc: retrievedAt,
    stale: Boolean(record.stale),
    unverified: source === "unknown" || Boolean(record.unverified),
    warning,
    provenance: /** @type {JsonObject} */ (detachJsonValue(provenance)),
    models,
  };
}

/**
 * Prefer the canonical versioned envelope and tolerate legacy projected model arrays
 * while an older local backend is being upgraded.
 *
 * @param {unknown} providerValue
 * @param {string} [providerId]
 * @returns {ProviderModelCatalogEnvelope | null}
 */
export function providerModelCatalog(providerValue, providerId = "") {
  const provider = asRecord(providerValue);
  const canonical = normalizeProviderModelCatalog(provider.model_catalog, providerId);
  if (canonical) return canonical;
  const legacyModels = provider.models || provider.model_options || provider.available_models;
  if (!Array.isArray(legacyModels)) return null;
  return normalizeProviderModelCatalog({
    provider_id: providerId,
    source: "unknown",
    origin: "unknown",
    stale: false,
    unverified: true,
    warning: null,
    provenance: {},
    models: legacyModels,
  }, providerId);
}

/**
 * @param {ProviderModelOption} option
 * @returns {string[]}
 */
export function providerModelIds(option) {
  if (typeof option === "string") return [option.trim()].filter(Boolean);
  const aliases = Array.isArray(option.aliases) ? option.aliases : [];
  return [
    option.id,
    option.model,
    option.value,
    option.display_name,
    option.name,
    option.canonical_model_id,
    option.docs_slug,
    option.build_slug,
    ...aliases,
  ].filter(Boolean).map((value) => String(value).trim()).filter(Boolean);
}

/**
 * @param {unknown} providerValue
 * @param {string} modelId
 * @param {string} [providerId]
 * @returns {ProviderModelOption | null}
 */
export function findProviderCatalogModel(providerValue, modelId, providerId = "") {
  const selected = String(modelId || "").trim();
  if (!selected) return null;
  const catalog = providerModelCatalog(providerValue, providerId);
  return catalog?.models.find((option) => providerModelIds(option).includes(selected)) || null;
}

/**
 * @param {string | null} value
 * @returns {string}
 */
function formatRetrievedAt(value) {
  if (!value) return "";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  /** @param {string} type */
  const part = (type) => parts.find((item) => item.type === type)?.value || "";
  return `${part("day")} ${part("month")} ${part("year")} at ${part("hour")}:${part("minute")} UTC`;
}

/**
 * @param {ProviderCatalogSource} source
 * @param {ProviderCatalogOrigin | ""} origin
 */
function sourceDescription(source, origin) {
  if (source === "live") return "live from discovery";
  if (source === "persisted" && origin === "live") return "saved from live discovery";
  if (source === "persisted" && origin === "bundled") return "saved bundled fallback";
  if (source === "persisted") return "saved locally";
  if (source === "bundled") return "bundled fallback";
  return "unverified";
}

/**
 * @param {ProviderModelCatalogStatusOptions} options
 * @returns {ProviderModelCatalogStatus}
 */
export function describeProviderModelCatalog(options) {
  const catalog = options.catalog;
  const refreshState = options.refreshState || {};
  const providerLabel = String(options.providerLabel || catalog?.provider_id || "Provider").trim();
  const selectedModel = String(options.selectedModel || "").trim();
  const visibleDetails = [];
  const accessibleDetails = [];
  let error = false;
  let warning = false;
  let membership = /** @type {ProviderModelCatalogStatus["modelMembership"]} */ ("");

  let catalogDescription = "";
  if (catalog) {
    catalogDescription = sourceDescription(catalog.source, catalog.origin);
    const retrievedAt = formatRetrievedAt(catalog.retrieved_at_utc);
    if (retrievedAt) catalogDescription += `, retrieved ${retrievedAt}`;
    if (catalog.stale) {
      visibleDetails.push("Catalog data is stale.");
      warning = true;
    }
    if (catalog.unverified) {
      visibleDetails.push("Availability is unverified.");
      warning = true;
    }
    if (catalog.warning) {
      accessibleDetails.push(catalog.warning);
      warning = true;
    }
    if (selectedModel) {
      const listed = catalog.models.some((option) => providerModelIds(option).includes(selectedModel));
      if (options.manual) {
        membership = listed ? "manual" : "unlisted";
        visibleDetails.push(listed ? "Manual model selected." : "Manual model selected; it is not listed in this catalog.");
        warning ||= !listed;
      } else {
        membership = listed ? "catalog" : "unlisted";
        if (!listed) {
          visibleDetails.push("Selected model is not listed in this catalog.");
          warning = true;
        }
      }
    }
  } else if (selectedModel && options.manual) {
    membership = "manual";
    visibleDetails.push("Manual model selected.");
  }

  const refreshStatus = String(refreshState.status || "");
  const enrichment = isRecord(refreshState.enrichment) ? asRecord(refreshState.enrichment) : {};
  const enrichmentStatus = String(enrichment.status || "");
  if (enrichmentStatus === "running") {
    visibleDetails.push("Live model list ready; updating model details in the background.");
  } else if (enrichmentStatus === "failed") {
    visibleDetails.push("Model details could not be updated; live availability remains current.");
    accessibleDetails.push(String(enrichment.error || "Model metadata enrichment failed."));
    warning = true;
  }
  if (!options.running && refreshStatus === "skipped_missing_api_key") {
    visibleDetails.push("Refresh needs an API key.");
    warning = true;
  }
  if (!options.running && refreshStatus === "failed") {
    visibleDetails.unshift("Refresh failed; using the available fallback.");
    accessibleDetails.push(String(refreshState.last_error || "Refresh failed."));
    error = true;
  }
  if (!options.running && refreshStatus === "configuration_error") {
    visibleDetails.unshift("Provider endpoint configuration is invalid; using the available catalog.");
    accessibleDetails.push(String(
      refreshState.configuration_error ||
      refreshState.last_error ||
      "Provider endpoint configuration is invalid.",
    ));
    error = true;
  }

  const lead = options.running
    ? catalogDescription
      ? `${providerLabel} model catalog: refreshing; currently ${catalogDescription}.`
      : `${providerLabel} model catalog: refreshing.`
    : catalogDescription
      ? `${providerLabel} model catalog: ${catalogDescription}.`
      : `${providerLabel} model catalog is unavailable.`;
  const text = [lead, ...visibleDetails].join(" ");
  const detail = [text, ...accessibleDetails].join(" ");

  return {
    text,
    detail,
    error,
    warning: warning && !error,
    source: catalog?.source || "",
    origin: catalog?.origin || "",
    stale: Boolean(catalog?.stale),
    unverified: Boolean(catalog?.unverified),
    modelMembership: membership,
  };
}
