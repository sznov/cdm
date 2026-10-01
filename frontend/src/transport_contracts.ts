import type {
  ConnectionState,
  JsonObject,
  RunEventEnvelopeV2,
  RunSnapshot as CanonicalRunSnapshot,
  RunState,
  RunStatus,
  SnapshotRunRecord,
  SnapshotSummary,
  SnapshotTraceRecord,
} from "./run_contracts.js";

export type MaybePromise<T> = T | PromiseLike<T>;

export type JsonRequestInput = RequestInfo | URL;

export type FetchJson = <TResponse = JsonObject>(
  input: JsonRequestInput,
  init?: RequestInit,
) => Promise<TResponse | null>;

export interface ApiErrorInit {
  status: number;
  statusText: string;
  url: string;
  responseText: string;
  payload: unknown;
}

export interface ApiErrorSurface extends Error, ApiErrorInit {
  readonly name: "ApiError";
}

export type SseEventHandler = (event: string, payload: unknown) => void;

export interface StreamSseOptions {
  method?: string;
  networkErrorMessage?: string;
  onEvent?: SseEventHandler;
  payload?: JsonObject;
}

export interface RunRequestCommon {
  retry_of_job_id?: string;
  session_id: string | null;
}

export interface WorkflowRuntimeConfig {
  auto_correction_sequence?: boolean;
  batch_retries?: number;
  completion_check?: boolean;
  correction_template_id?: string | null;
  direct_microop_judge?: boolean;
  infer_implicit_identifiers?: boolean;
  language_repair?: boolean;
  max_attempts?: number | null;
  max_correction_operations?: number | null;
  max_iterations?: number;
  no_progress_iterations?: number;
  prompt_profile?: string;
  semantic_critic?: boolean;
  think?: boolean | null;
}

export interface RuntimeModelBinding {
  base_url?: string | null;
  max_completion_tokens?: number | null;
  model: string;
  model_parameters?: JsonObject;
  provider: string;
  provider_options?: JsonObject;
  reasoning_effort?: string | null;
  temperature?: number | null;
  timeout_seconds?: number;
  top_p?: number | null;
}

export interface RuntimeModelBindings {
  default: RuntimeModelBinding;
}

export interface StartupRecoverySummary extends JsonObject {
  archived_store: boolean;
  message: string;
  occurred: boolean;
  operation: "archive_store" | "quarantine" | null;
  quarantined_runs: number;
  quarantined_sessions: number;
  reason_counts: Record<string, number>;
  recovery_id: string | null;
}

export interface DegradedRunSummary extends JsonObject {
  attempts: number;
  detected_at_utc: string;
  error_type: string;
  reason: "terminal_persistence_failed";
  run_id: string;
}

export interface CoordinatorHealthSummary extends JsonObject {
  admission: "accepting" | "paused" | "closed";
  admission_expires_at_utc: string | null;
  admission_generation: number | null;
  degraded_count: number;
  degraded_runs: DegradedRunSummary[];
  operation_counts: {
    draining: number;
    provider_backed: number;
    total: number;
  };
  status: "ok" | "degraded" | "unavailable";
}

export interface ApplicationHealth extends JsonObject {
  app: string;
  coordinator: CoordinatorHealthSummary;
  ok: boolean;
}

export interface ApplicationRuntimeConfig extends JsonObject {
  default_runtime_harness_id: string;
  startup_recovery: StartupRecoverySummary;
}

export interface RuntimeSessionRequestProjection {
  harness_runtime_config?: WorkflowRuntimeConfig;
  model_bindings?: RuntimeModelBindings;
  runtime_harness_id?: string;
  session_id?: string;
  specification?: string;
}

export interface FreshRunRequest extends RunRequestCommon {
  harness_definition_revision?: string;
  harness_runtime_config: WorkflowRuntimeConfig;
  model_bindings: RuntimeModelBindings;
  runtime_harness_id: string;
  specification: string;
  resume_from_job_id?: never;
  resume_trace_index?: never;
}

export interface ResumeRunRequest extends RunRequestCommon {
  resume_from_job_id: string;
  resume_trace_index?: number;
  harness_definition_revision?: never;
  harness_runtime_config?: never;
  model_bindings?: never;
  runtime_harness_id?: never;
  specification?: never;
}

export type CreateRunRequest = FreshRunRequest | ResumeRunRequest;

export interface CreateSessionRequest {
  harness_definition_revision?: string;
  harness_runtime_config: WorkflowRuntimeConfig;
  model_bindings: RuntimeModelBindings;
  runtime_harness_id: string;
  specification: string;
  title?: string;
}

export interface CreateRunResponse {
  events_url: string;
  run_id: string;
  session_id: string | null;
  snapshot_url: string;
  status: RunStatus;
}

export interface RunSnapshotRequest {
  cache?: RequestCache;
  includeTrace?: boolean;
  runId: string;
}

export type RunSnapshotRecord = SnapshotRunRecord;

export type RunSnapshotSummary = SnapshotSummary;

export type RunTraceRecord = SnapshotTraceRecord;

export interface RunSnapshot extends CanonicalRunSnapshot {
  decision_patches?: JsonObject[];
}

export interface RunSnapshotProjection extends Omit<RunSnapshot, "snapshot_sequence" | "trace"> {
  run?: Omit<RunSnapshotRecord, "snapshot_sequence">;
}

export interface RunTracePageRequest {
  after?: number;
  cursor?: string;
  limit: number;
}

export interface RunTracePage {
  after?: number;
  has_more?: boolean;
  job_id: string;
  limit?: number;
  next_after?: number;
  next_cursor?: string | null;
  summary?: RunSnapshotSummary;
  trace: RunTraceRecord[];
}

export type RunConnectionState = ConnectionState;

export type RunRouteReason = "accepted" | "duplicate" | "gap" | "invalid";

export interface AcceptedRunRouteResult {
  accepted: true;
  reason: "accepted";
  rendered?: boolean;
  runId: string;
  sequence: number;
  terminal: boolean;
}

export interface RejectedRunRouteResult {
  accepted: false;
  expectedSequence?: number;
  lastAppliedSequence?: number;
  reason: Exclude<RunRouteReason, "accepted">;
  runId: string;
  runState?: RunState;
  sequence: number;
  terminal?: false;
}

export type RunRouteResult = AcceptedRunRouteResult | RejectedRunRouteResult;

export interface EventSourceLike {
  close(): void;
  onerror: ((event: Event) => unknown) | null;
  onmessage: ((event: MessageEvent<string>) => unknown) | null;
  onopen: ((event: Event) => unknown) | null;
}

export type EventSourceFactory = (url: string) => EventSourceLike;

export interface RunObserveOptions {
  eventsUrl?: string;
  forceHydrate?: boolean;
  hydrate?: boolean;
  rebuildPresentation?: boolean;
  snapshot?: RunSnapshot | null;
  snapshotUrl?: string;
}

export type RunSnapshotLoader = (snapshotUrl: string, runId: string) => Promise<RunSnapshot>;

export type RunTracePageLoader = (
  runId: string,
  request: RunTracePageRequest,
) => Promise<RunTracePage>;

export type RunEnvelopeRouter = (envelope: RunEventEnvelopeV2) => RunRouteResult;

export type RunHistoryHydrator = (
  runId: string,
  after: number,
  through: number,
  snapshot: RunSnapshot | null,
) => Promise<number>;

export interface RunObservationControllerOptions {
  eventSourceFactory?: EventSourceFactory;
  getRunSnapshot: RunSnapshotLoader;
  getRunState: (runId: string) => RunState;
  getRunTracePage?: RunTracePageLoader;
  hydrateHistory?: RunHistoryHydrator;
  hydrateRunSnapshot: (snapshot: RunSnapshotProjection) => RunState | null;
  onConnectionChange?: (runId: string, state: RunState) => void;
  onTerminal?: (runId: string, envelope: RunEventEnvelopeV2) => MaybePromise<unknown>;
  rebuildPresentation?: (
    runId: string,
    trace: RunState["trace"],
    snapshot: RunSnapshot | null,
  ) => MaybePromise<unknown>;
  routeEnvelope: RunEnvelopeRouter;
  routeHistoryEnvelope?: RunEnvelopeRouter;
}

export interface RunObservationController {
  closeAll(): void;
  closeRun(runId: string, connectionState?: RunConnectionState | null): void;
  isObserving(runId: string): boolean;
  observeRun(runId: string, options?: RunObserveOptions): Promise<RunState | null>;
  observedRunIds(): string[];
}

export interface RuntimeHarnessSummary {
  definition_revision?: string;
  id?: string;
  name?: string;
  runnable?: boolean;
}

export interface RecordedRunProjection {
  effective_harness_run_spec?: {
    harness_id?: string;
  };
  runtime_harness_id?: string;
  runtime_harness_name?: string;
  session_id?: string | null;
}

export interface PrepareRunOptions {
  resumeFromJobId?: string;
  resumeRunRecord?: RecordedRunProjection | null;
  resumeTraceIndex?: number;
  retryOfJobId?: string;
  retryRunRecord?: RecordedRunProjection | null;
  sessionId?: string | null;
}

export interface RunStreamElements {
  jobInfo?: Pick<HTMLElement, "textContent"> | null;
  runIdBadge?: Pick<HTMLElement, "textContent"> | null;
  runtimeHarnessSelect?: Pick<HTMLSelectElement, "value"> | null;
  specification?: Pick<HTMLTextAreaElement, "value"> | null;
}

export interface RunStreamRequestContext {
  currentSession(): RuntimeSessionRequestProjection | null;
  elements: RunStreamElements;
  selectedSessionId(): string | null;
  setStatus(message: string): void;
}

export interface PreparedRunRequest {
  isResume: boolean;
  payload: CreateRunRequest;
  preserveTraceUntilStart: boolean;
  runtimeId: string;
}
