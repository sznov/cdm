export function handleStreamModelAnalysisEvent(context, event, payload) {
  if (event === "artifact_extraction") {
    const summary = payload.ok
      ? `${payload.item_count || 0} artifact strings extracted.`
      : `Extractor failed: ${payload.error || "invalid output"}`;
    context.setStatus(`Artifact extraction attempt ${payload.attempt}: ${payload.ok ? "ok" : "failed"}.`);
    context.addTraceEntry({
      event,
      agentId: "artifactExtractor",
      title: `Artifact extraction ${payload.attempt}`,
      summary,
      output: payload.raw_output || "",
      payload,
      status: payload.ok ? "accepted" : "rejected",
    });
    return true;
  }
  if (event === "context_analysis") {
    const hasError = Boolean(payload.error);
    context.setStatus(hasError ? `Context analysis failed: ${payload.error}` : "Context analysis notes ready.");
    context.addTraceEntry({
      event,
      agentId: "contextAnalyst",
      title: "Context analysis",
      summary: hasError ? payload.error : "Freeform modeling notes for the operation agent.",
      output: payload.raw_output || payload.notes || "",
      payload,
      status: hasError ? "error" : "accepted",
    });
    return true;
  }
  if (event === "change_requests_planned") {
    const requestCount = payload.change_request_count || payload.fallback_change_request_count || payload.change_requests?.length || 0;
    context.setStatus(`Change planner produced ${requestCount} request(s).`);
    context.addTraceEntry({
      event,
      agentId: "changePlanner",
      title: "Change requests planned",
      summary: `${requestCount} free-form change request(s).`,
      output: payload.raw_output || "",
      payload,
      status: payload.ok ? "accepted" : "fallback",
    });
    return true;
  }
  if (event === "tool_calls_split") {
    context.addTraceEntry({
      event,
      agentId: "toolSplitter",
      title: "Tool calls split",
      summary: `${payload.tool_call_count || 0} tool calls found in one output.`,
      payload,
    });
    return true;
  }
  if (event === "language_name_repair") {
    if (payload.changed) {
      const changes = (payload.changes || []).map((item) => `${item.from} -> ${item.to}`).join(", ");
      context.setStatus(`Language name repair: ${changes}`);
    }
    context.addTraceEntry({
      event,
      agentId: "languageRepair",
      title: "Language repair",
      summary: payload.changed ? "Names changed before validation." : "Repair step ran, but made no changes.",
      payload,
      status: payload.changed ? "changed" : "unchanged",
    });
    return true;
  }
  if (event === "semantic_operation_critic") {
    const accepted = payload.accepted !== false;
    const summary = accepted
      ? (payload.reason || "Operation is semantically supported.")
      : (payload.feedback || payload.reason || "Operation is not semantically supported.");
    context.setStatus(`Semantic critic: ${accepted ? "accepted" : "rejected"}. ${summary}`);
    context.addTraceEntry({
      event,
      agentId: "semanticCritic",
      title: `Semantic critic ${payload.iteration}.${payload.batch_attempt}`,
      summary,
      output: payload.raw_output || "",
      payload,
      status: accepted ? "accepted" : "rejected",
    });
    return true;
  }
  if (event === "completion_check") {
    const outcome = payload.complete ? "complete" : "incomplete";
    const nextFocus = payload.next_focus ? ` Next: ${payload.next_focus}` : "";
    context.setStatus(`Completion check: ${outcome}.${nextFocus}`);
    context.addTraceEntry({
      event,
      agentId: "completionCheck",
      title: "Completion check",
      summary: `${outcome}${nextFocus}`,
      payload,
      status: outcome,
    });
    return true;
  }
  return false;
}
