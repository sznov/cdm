export type JsonPrimitive = boolean | number | string | null;

export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export type JsonObject = { [key: string]: JsonValue };

export type StructuredAttributeType = "string" | "int" | "real" | "bool" | "date";

export type StructuredMultiplicity = "0..1" | "1" | "0..*" | "*" | "1..*";

export type StructuredIdentifierPartKind = "attribute" | "relationship";

export interface StructuredAttribute {
  readonly name: string;
  readonly type: StructuredAttributeType;
}

export interface StructuredIdentifierPart {
  readonly kind: StructuredIdentifierPartKind;
  readonly ref: string;
}

export interface StructuredEntity {
  readonly name: string;
  readonly attributes: readonly StructuredAttribute[];
  readonly identifier: readonly StructuredIdentifierPart[];
  readonly inherits_from: readonly string[];
}

export interface StructuredRelationshipEnd {
  readonly entity: string;
  readonly multiplicity: StructuredMultiplicity | null;
  readonly role: string | null;
}

export interface StructuredRelationship {
  readonly name: string | null;
  readonly source: StructuredRelationshipEnd;
  readonly target: StructuredRelationshipEnd;
}

export interface StructuredModel {
  readonly entities: readonly StructuredEntity[];
  readonly relationships: readonly StructuredRelationship[];
}

export type RunStatus =
  | ""
  | "created"
  | "queued"
  | "running"
  | "cancelling"
  | "completed"
  | "done"
  | "failed"
  | "error"
  | "cancelled"
  | "canceled"
  | "interrupted"
  | "unavailable";

export type RunPathReferenceMode = "run_relative_v1";

export type ConnectionState =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "desynced"
  | "closed";

export type RunOperationKind = "correction" | "correction_sequence" | "decision" | "operation" | "question";

export interface PendingRunOperation {
  readonly id: string;
  readonly kind: RunOperationKind;
  readonly startedAt: number;
}

export interface RunEventEnvelopeV2 {
  readonly schema_version: 2;
  readonly run_id: string;
  readonly session_id: string | null;
  readonly sequence: number;
  readonly type: string;
  readonly timestamp_utc: string;
  readonly payload: JsonObject;
}

export interface DiagramViewport {
  readonly zoom?: number;
  readonly scrollLeft: number;
  readonly scrollTop: number;
  readonly scrollLeftRatio?: number;
  readonly scrollTopRatio?: number;
}

export interface RunArtifacts {
  workingModel: JsonValue | null;
  structuredModel: StructuredModel | null;
  plantuml: string;
  plantumlUrl: string;
}

export interface RunState {
  runId: string;
  status: RunStatus;
  phase: string;
  output: string;
  trace: RunEventEnvelopeV2[];
  presentationTrace: JsonObject[];
  artifacts: RunArtifacts;
  viewport: DiagramViewport | null;
  connectionState: ConnectionState;
  lastAppliedSequence: number;
  error: string | null;
  pendingOperation: PendingRunOperation | null;
}

export interface RunStateSeed {
  status?: RunStatus;
  phase?: string;
  output?: string;
  trace?: RunEventEnvelopeV2[];
  presentationTrace?: JsonObject[];
  artifacts?: Partial<RunArtifacts>;
  viewport?: DiagramViewport | null;
  connectionState?: ConnectionState;
  lastAppliedSequence?: number;
  error?: string | null;
  pendingOperation?: PendingRunOperation | null;
}

export interface RunStateStore {
  runsById: Record<string, RunState>;
  selectedRunId: string | null;
}

export interface SnapshotResult {
  output?: string;
  raw_output?: string;
  working_model?: JsonValue | null;
  model_snapshot?: JsonValue | null;
  structured_model?: StructuredModel | null;
  plantuml?: string;
  plantuml_url?: string;
}

export interface SnapshotRunRecord extends SnapshotResult {
  job_id?: string;
  run_id?: string;
  session_id?: string | null;
  status?: RunStatus;
  phase?: string;
  snapshot_sequence?: number;
  result?: SnapshotResult;
  viewport?: DiagramViewport | null;
  connection_state?: ConnectionState;
  error?: string | null;
  path_reference_mode?: RunPathReferenceMode;
  record_available?: boolean;
  trace_available?: boolean;
  trace_event_count?: number;
}

export interface SnapshotSummary {
  job_id?: string;
  run_id?: string;
  session_id?: string | null;
  status?: RunStatus;
  record_available?: boolean;
  trace_available?: boolean;
  trace_event_count?: number;
}

export interface SnapshotTraceRecord {
  schema_version?: number;
  run_id?: string;
  session_id?: string | null;
  sequence?: number;
  type?: string;
  event?: string;
  timestamp_utc?: string;
  payload?: JsonObject;
}

export interface RunSnapshot extends SnapshotResult {
  schema_version?: number;
  run_id?: string;
  job_id?: string;
  session_id?: string | null;
  status?: RunStatus;
  snapshot_sequence?: number;
  phase?: string;
  trace?: SnapshotTraceRecord[];
  run?: SnapshotRunRecord;
  summary?: SnapshotSummary;
  result?: SnapshotResult;
  viewport?: DiagramViewport | null;
  connection_state?: ConnectionState;
  error?: string | null;
}

export interface InvalidEventAdmission {
  readonly accepted: false;
  readonly reason: "invalid";
  readonly runId: string;
  readonly sequence: number;
}

export interface DuplicateEventAdmission {
  readonly accepted: false;
  readonly reason: "duplicate";
  readonly runId: string;
  readonly sequence: number;
  readonly runState: RunState;
}

export interface GapEventAdmission {
  readonly accepted: false;
  readonly reason: "gap";
  readonly runId: string;
  readonly sequence: number;
  readonly expectedSequence: number;
  readonly runState: RunState;
}

export interface AcceptedEventAdmission {
  readonly accepted: true;
  readonly reason: "accepted";
  readonly runId: string;
  readonly sequence: number;
  readonly eventType: string;
  readonly payload: JsonObject;
  readonly envelope: RunEventEnvelopeV2;
  readonly runState: RunState;
  readonly wasDesynced: boolean;
}

export type EventAdmission =
  | AcceptedEventAdmission
  | DuplicateEventAdmission
  | GapEventAdmission
  | InvalidEventAdmission;

export interface RunEventReductionOptions {
  readonly appendTrace?: boolean;
  readonly applyPayload?: boolean;
}

export interface DebugRunStateSnapshot {
  runId: string;
  status: RunStatus;
  phase: string;
  output: string;
  trace: RunEventEnvelopeV2[];
  connectionState: ConnectionState;
  lastAppliedSequence: number;
  error: string | null;
  pendingOperation: PendingRunOperation | null;
}

export interface AppDebugSnapshot {
  selectedRunId: string | null;
  runsById: Record<string, DebugRunStateSnapshot>;
}

export interface AppDebugBridge {
  beginRunOperation(runId: string, kind: RunOperationKind): PendingRunOperation | null;
  finishRunOperation(runId: string, operationId: string): boolean;
  selectRun(runId: string): void;
  stateSnapshot(): AppDebugSnapshot;
}
