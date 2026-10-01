export function handleStructuredDraftEvent(context, event, payload) {
  if (event === "direct_baseline_validation") {
    const accepted = Boolean(payload.accepted);
    if (accepted) context.applyModelSnapshotPayload(payload);
    context.setStatus(accepted ? payload.summary || "Direct baseline model validated." : payload.summary || "Direct baseline model failed validation.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "directBaseline",
      title: `Direct baseline validation ${payload.batch_attempt || 1}`,
      summary: accepted ? payload.summary || "Direct baseline model validated." : payload.error || "Direct baseline model failed validation.",
      payload,
      status: accepted ? "accepted" : "rejected",
      modelSnapshot: accepted ? payload.model_snapshot : null,
      plantuml: accepted ? payload.plantuml : "",
      plantumlUrl: accepted ? payload.plantuml_url : "",
    });
    return true;
  }
  if (event === "draft_model_validation") {
    const accepted = Boolean(payload.accepted);
    if (accepted) context.applyModelSnapshotPayload(payload);
    context.setStatus(accepted ? payload.summary || "Draft model validated." : payload.summary || "Draft model failed validation.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "structuredValidator",
      title: `Draft validation ${payload.batch_attempt || 1}`,
      summary: accepted ? payload.summary || "Draft model validated." : payload.error || "Draft model failed validation.",
      payload,
      status: accepted ? "accepted" : "rejected",
      modelSnapshot: accepted ? payload.model_snapshot : null,
      plantuml: accepted ? payload.plantuml : "",
      plantumlUrl: accepted ? payload.plantuml_url : "",
    });
    return true;
  }
  if (event === "draft_model_retry_feedback") {
    context.setStatus(payload.summary || "Draft validation feedback appended for retry.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "structuredValidator",
      title: `Draft retry feedback ${payload.batch_attempt || "?"}`,
      summary: payload.summary || "Validation feedback appended to the draft model chat.",
      output: payload.feedback || "",
      payload,
      status: "running",
    });
    return true;
  }
  if (event === "structured_language_repair_applied") {
    context.applyModelSnapshotPayload(payload);
    context.setStatus(payload.summary || "Structured language repair applied.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "structuredLanguageRepair",
      title: "Structured language repair applied",
      summary: payload.summary || `${payload.applied_count || 0} rename suggestion(s) applied.`,
      payload,
      status: payload.error ? "rejected" : "accepted",
      modelSnapshot: payload.model_snapshot,
      plantuml: payload.plantuml,
      plantumlUrl: payload.plantuml_url,
    });
    return true;
  }
  return false;
}
