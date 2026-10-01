export function handleStructuredCoverageEvent(context, event, payload) {
  if (event === "plan_coverage_critic_result") {
    const hasError = Boolean(payload.error);
    context.setStatus(payload.summary || (hasError ? "Coverage critic failed." : "Coverage critic produced findings."));
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "planCoverageCritic",
      title: hasError ? "Coverage critic failed" : "Coverage critic result",
      summary: payload.summary || `${payload.finding_count || 0} finding(s).`,
      payload,
      status: hasError ? "rejected" : "accepted",
    });
    return true;
  }
  if (event === "plan_coverage_critic_findings") {
    context.setStatus(payload.summary || "Plan coverage critic produced findings.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "planCoverageCritic",
      title: "Plan coverage findings",
      summary: payload.summary || `${payload.finding_count || 0} finding(s).`,
      payload,
      status: payload.error ? "rejected" : "accepted",
    });
    return true;
  }
  if (event === "critic_patch_tasks_planned") {
    const hasError = Boolean(payload.error);
    context.setStatus(payload.summary || (hasError ? "Patch task planning failed." : "Patch tasks planned."));
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "criticPatchPlanner",
      title: hasError ? "Patch task planning failed" : "Patch tasks planned",
      summary: payload.summary || `${payload.task_count || 0} patch task(s).`,
      payload,
      status: hasError ? "rejected" : "accepted",
    });
    return true;
  }
  if (event === "semantic_patch_validation_result") {
    const accepted = Boolean(payload.accepted);
    context.setStatus(payload.summary || (accepted ? "Semantic patch accepted." : "Semantic patch rejected."));
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "semanticPatchValidator",
      title: accepted ? `Semantic patch ${payload.task_id || ""} accepted` : `Semantic patch ${payload.task_id || ""} rejected`,
      summary: payload.summary || payload.error || "",
      payload,
      status: accepted ? "accepted" : "rejected",
    });
    return true;
  }
  if (event === "atomic_model_patch_validation") {
    const accepted = Boolean(payload.accepted);
    if (accepted) context.applyModelSnapshotPayload(payload);
    context.setStatus(payload.summary || (accepted ? "Atomic patch accepted." : "Atomic patch rejected."));
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "structuredValidator",
      title: accepted ? `Atomic patch ${payload.task_id || ""} accepted` : `Atomic patch ${payload.task_id || ""} rejected`,
      summary: payload.summary || payload.error || "",
      payload,
      status: accepted ? "accepted" : "rejected",
      modelSnapshot: payload.model_snapshot,
      plantuml: payload.plantuml,
      plantumlUrl: payload.plantuml_url,
    });
    return true;
  }
  if (event === "atomic_model_patch_retry_feedback") {
    context.setStatus(payload.summary || "Atomic patch retry feedback appended.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "structuredValidator",
      title: `Atomic patch ${payload.task_id || ""} retry feedback`,
      summary: payload.summary || "",
      payload,
      status: "running",
    });
    return true;
  }
  if (event === "critic_model_patch_validation") {
    const accepted = Boolean(payload.accepted);
    context.setStatus(payload.summary || (accepted ? "Critic patch accepted." : "Critic patch rejected."));
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "structuredValidator",
      title: accepted ? "Critic patch accepted" : "Critic patch rejected",
      summary: payload.summary || payload.error || "",
      payload,
      status: accepted ? "accepted" : "rejected",
    });
    return true;
  }
  return false;
}
