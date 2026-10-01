import {
  normalizedTraceIndex,
} from './run_session_state.js';
import {
  sourceSessionForRunRecord,
} from './retry_branching_source.js';

function selectedRunId(context) {
  return context.selectedRunId?.() || "";
}

export async function fetchRunRecord(context, jobId) {
  const payload = await context.getRun(jobId);
  return payload.run || {};
}

export async function retryTargetForTraceEntry(context, entry, runRecord) {
  const event = String(entry?.event || "");
  const payload = entry?.payload || {};
  const request = runRecord?.request || {};
  const selectedJobId = selectedRunId(context);
  const entryTraceIndex = normalizedTraceIndex(entry?.trace_index);
  if (event !== "resume_from_checkpoint") {
    return {
      sourceJobId: selectedJobId,
      sourceTraceIndex: entryTraceIndex,
      sourceRunRecord: runRecord,
      sourceTitle: context.sessionDisplayTitle(sourceSessionForRunRecord(context, runRecord), runRecord) || runRecord?.title || "",
    };
  }

  const sourceJobId = payload.source_job_id || request.resume_from_job_id || selectedJobId;
  const sourceTraceIndex =
    normalizedTraceIndex(payload.source_trace_index) ??
    normalizedTraceIndex(request.resume_trace_index) ??
    entryTraceIndex;
  if (!sourceJobId) {
    throw new Error("Cannot branch from this resume marker because its source run is unknown.");
  }
  const sourceRunRecord = sourceJobId === selectedJobId ? runRecord : await fetchRunRecord(context, sourceJobId);
  const sourceTitle =
    context.sessionDisplayTitle(sourceSessionForRunRecord(context, sourceRunRecord), sourceRunRecord) ||
    sourceRunRecord?.title ||
    context.shortRunId(sourceJobId);
  return { sourceJobId, sourceTraceIndex, sourceRunRecord, sourceTitle };
}
