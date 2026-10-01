import {
  basenamePath,
} from './format.js';
import { appendHistoryView } from './history_view.js';
import { agentIdForModelCallKind } from './stream_event_metadata.js';

export function handleStreamModelRuntimeEvent(context, event, payload) {
  if (event === "operation_batch_applied") {
    appendHistoryView(context.elements, payload);
    const accepted = payload.accepted?.length ?? 0;
    const rejected = payload.rejected?.length ?? 0;
    context.addTraceEntry({
      event,
      agentId: "validator",
      title: `Validation ${payload.iteration}.${payload.batch_attempt}`,
      summary: `${accepted} accepted, ${rejected} rejected`,
      payload,
      status: rejected ? "rejected" : "accepted",
    });
    return true;
  }
  if (event === "model_call_log") {
    const compactPath = basenamePath(payload.path);
    if (payload.path && context.elements.jobInfo) {
      context.elements.jobInfo.textContent = `Job ${payload.job_id} | latest log: ${compactPath}`;
    }
    context.addTraceEntry({
      event,
      agentId: agentIdForModelCallKind(payload.kind),
      title: "Model call log written",
      summary: compactPath || "Model call persisted.",
      payload,
    });
    return true;
  }
  if (event === "checkpoint_written") {
    const compactPath = basenamePath(payload.path);
    context.setStatus(payload.summary || `Checkpoint written: ${compactPath || payload.stage || "checkpoint"}.`);
    context.addTraceEntry({
      event,
      agentId: "runtime",
      title: `Checkpoint ${payload.stage || ""}`.trim(),
      summary: payload.summary || compactPath || "Stage checkpoint persisted.",
      payload,
      status: "checkpoint",
    });
    return true;
  }
  if (event === "resume_from_checkpoint") {
    context.applyModelSnapshotPayload(payload);
    context.setStatus(payload.summary || `Resuming from ${payload.stage || "checkpoint"}.`);
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "runtime",
      title: `Resume ${payload.stage || ""}`.trim(),
      summary: payload.summary || "Run resumed from a persisted checkpoint.",
      payload,
      status: "resume",
      modelSnapshot: payload.model_snapshot,
      plantuml: payload.plantuml,
      plantumlUrl: payload.plantuml_url,
    });
    return true;
  }
  return false;
}
