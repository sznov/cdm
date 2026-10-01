import type { JsonObject, JsonValue } from "./run_contracts.js";

export type ProviderCatalogSource = "live" | "persisted" | "bundled" | "unknown";

export type ProviderCatalogOrigin = "live" | "bundled" | "unknown";

export type ProviderCatalogEnrichmentStatus = "idle" | "running" | "succeeded" | "failed";

export interface ProviderCatalogEnrichmentState {
  readonly status: ProviderCatalogEnrichmentStatus;
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly error: string | null;
}

export interface ProviderCatalogRefreshState {
  readonly status?: string;
  readonly last_error?: string | null;
  readonly configuration_error?: string | null;
  readonly enrichment?: ProviderCatalogEnrichmentState;
}

export interface ProviderModelDescriptor {
  readonly id?: string;
  readonly model?: string;
  readonly value?: string;
  readonly name?: string;
  readonly label?: string;
  readonly display_name?: string;
  readonly canonical_model_id?: string;
  readonly docs_slug?: string;
  readonly build_slug?: string;
  readonly aliases?: readonly string[];
  readonly [key: string]: unknown;
}

export type ProviderModelOption = string | ProviderModelDescriptor;

export interface ProviderModelCatalogEnvelope {
  readonly schema_version: number | null;
  readonly provider_id: string;
  readonly source: ProviderCatalogSource;
  readonly origin: ProviderCatalogOrigin;
  readonly retrieved_at_utc: string | null;
  readonly stale: boolean;
  readonly unverified: boolean;
  readonly warning: string | null;
  readonly provenance: JsonObject;
  readonly models: readonly ProviderModelOption[];
}

export interface ProviderModelCatalogStatusOptions {
  readonly catalog: ProviderModelCatalogEnvelope | null;
  readonly providerLabel?: string;
  readonly refreshState?: Readonly<Record<string, unknown>>;
  readonly running?: boolean;
  readonly selectedModel?: string;
  readonly manual?: boolean;
}

export interface ProviderModelCatalogStatus {
  readonly text: string;
  readonly detail: string;
  readonly error: boolean;
  readonly warning: boolean;
  readonly source: ProviderCatalogSource | "";
  readonly origin: ProviderCatalogOrigin | "";
  readonly stale: boolean;
  readonly unverified: boolean;
  readonly modelMembership: "catalog" | "manual" | "unlisted" | "";
}

export interface ProviderConfigWithCatalog {
  readonly model_catalog?: unknown;
  readonly models?: unknown;
  readonly model_options?: unknown;
  readonly available_models?: unknown;
  readonly model_refresh?: Readonly<Record<string, unknown>>;
  readonly catalog_refresh?: Readonly<Record<string, unknown>>;
  readonly [key: string]: unknown;
}

export interface ProviderCatalogRefreshResponse extends Partial<ProviderModelCatalogEnvelope> {
  readonly catalog?: ProviderModelCatalogEnvelope;
  readonly state?: ProviderCatalogRefreshState & Readonly<Record<string, JsonValue>>;
}
