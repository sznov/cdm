import {
  formatJson,
} from './format.js';

export function handleStructuredDecisionEvent(context, event, payload) {
  if (event === "decision_patches") {
    context.updateDecisionPatches(payload.decision_patches || []);
    const patchCount = context.currentDecisionPatches().length;
    context.setStatus(payload.summary || `${patchCount} decision patch(es) available.`);
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "planCoverageCritic",
      title: "Decision patches available",
      summary: payload.summary || `${patchCount} optional modeling decision(s).`,
      output: formatJson(payload.decision_patches || []),
      payload,
      status: "decision",
    });
    return true;
  }
  if (event === "draft_model_issues") {
    if (payload.decision_patches) context.updateDecisionPatches(payload.decision_patches);
    context.setStatus(payload.summary || "Draft model reported issues.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "draftModeler",
      title: "Draft model issues",
      summary: payload.summary || `${(payload.issues || []).length} draft issue(s).`,
      output: formatJson(payload.issues || []),
      payload,
      status: payload.decision_patches?.length ? "decision" : "accepted",
    });
    return true;
  }
  if (event === "decision_patch_applied" || event === "decision_patch_batch_done" || event === "decision_patch_batch_start") {
    if (payload.decision_patches) context.updateDecisionPatches(payload.decision_patches);
    context.setStatus(payload.summary || "Decision patch update.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "incrementalOpApplier",
      title:
        event === "decision_patch_batch_start"
          ? "Decision patch batch started"
          : event === "decision_patch_batch_done"
          ? "Decision patch batch complete"
          : `Decision patch ${payload.status || "applied"}`,
      summary: payload.summary || payload.result?.reason || "",
      output: payload.result ? formatJson(payload.result) : "",
      payload,
      status: payload.status || "decision",
    });
    return true;
  }
  return false;
}
