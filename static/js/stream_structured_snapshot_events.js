export function handleStructuredSnapshotEvent(context, event, payload) {
  if (event === "partial_model_snapshot") {
    context.applyModelSnapshotPayload(payload);
    context.setStatus(payload.summary || `Diagram snapshot ${payload.diagram_version || ""}`.trim());
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "asyncPlantumlRenderer",
      title: `Diagram snapshot ${payload.diagram_version || ""}`.trim(),
      summary: payload.summary || "Intermediate model rendered.",
      payload,
      status: "accepted",
      modelSnapshot: payload.model_snapshot,
      plantuml: payload.plantuml,
      plantumlUrl: payload.plantuml_url,
    });
    return true;
  }
  if (event === "structured_model_validated") {
    context.applyModelSnapshotPayload(payload);
    if (payload.decision_patches) context.updateDecisionPatches(payload.decision_patches);
    context.setStatus(payload.summary || "Structured model validated.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "validator",
      title: "Structured model validated",
      summary: payload.summary || `${payload.entity_count || 0} entities, ${payload.relationship_count || 0} relationships.`,
      payload,
      status: "accepted",
      modelSnapshot: payload.model_snapshot,
      plantuml: payload.plantuml,
      plantumlUrl: payload.plantuml_url,
    });
    return true;
  }
  return false;
}
