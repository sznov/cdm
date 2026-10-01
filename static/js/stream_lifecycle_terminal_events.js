export function handleDoneEvent(context, event, payload) {
  if (event !== "done") return false;
  const isReplay = payload.__replay && context.loadingArchivedRun();
  if (!isReplay) {
    context.setLastRunTerminalStatus("done");
    context.setSelectedRunStatus("completed");
    const terminalJobId = payload.job_id || context.selectedRunId();
    context.markCurrentRunStatus?.("completed", terminalJobId);
    context.markCurrentSessionRunStatus("completed", terminalJobId);
    context.applyModelSnapshotPayload({
      model_snapshot: payload.working_model || context.currentWorkingModel(),
      structured_model: payload.structured_model || context.currentStructuredModel(),
      plantuml: payload.plantuml || context.currentPlantuml(),
      diagram_version: payload.diagram_version,
    });
    const decisionPatches = Array.isArray(payload.decision_patches)
      ? payload.decision_patches
      : context.currentDecisionPatches?.();
    if (Array.isArray(decisionPatches)) context.updateDecisionPatches(decisionPatches);
    context.setStatus(
      `Done ${payload.job_id}: ${payload.stop_reason}, ${payload.iterations} iterations, ` +
        `${payload.accepted_operation_count} accepted, ${payload.rejected_operation_count} rejected.`
    );
  }
  context.addTraceEntry({
    event,
    agentId: "renderer",
    title: "Run finished",
    summary: `${payload.stop_reason}: ${payload.accepted_operation_count} accepted, ${payload.rejected_operation_count} rejected`,
    output: payload.plantuml || "",
    payload,
    status: "done",
    modelSnapshot: payload.working_model,
    plantuml: payload.plantuml,
    plantumlUrl: payload.plantuml_url,
  });
  if (!isReplay) {
    context.loadRuns().catch((error) => console.warn("Could not refresh runs", error));
    context.loadSessions().catch((error) => console.warn("Could not refresh sessions", error));
  }
  return true;
}

export function handleCancelledEvent(context, event, payload) {
  if (event !== "cancelled") return false;
  context.setLastRunTerminalStatus("cancelled");
  context.setSelectedRunStatus("cancelled");
  const terminalJobId = payload.job_id || context.selectedRunId();
  context.markCurrentRunStatus?.("cancelled", terminalJobId);
  context.markCurrentSessionRunStatus("cancelled", terminalJobId);
  context.markCurrentGenerationInterrupted({
    ...payload,
    detail: payload.detail || "Run cancelled before generation completed.",
  });
  context.setStatus(`Stopped ${payload.job_id || context.selectedRunId() || "run"}: ${payload.detail || "cancelled"}`);
  context.addTraceEntry({
    event,
    agentId: "runtime",
    title: "Run stopped",
    summary: payload.detail || "Run cancelled.",
    payload,
    status: "cancelled",
  });
  if (!payload.__replay && !context.loadingArchivedRun()) {
    context.loadRuns().catch((error) => console.warn("Could not refresh runs", error));
    context.loadSessions().catch((error) => console.warn("Could not refresh sessions", error));
  }
  return true;
}

export function handleErrorEvent(context, event, payload) {
  if (event !== "error") return false;
  context.setLastRunTerminalStatus("error");
  const failedJobId = payload.job_id || context.selectedRunId() || "";
  if (failedJobId) {
    context.setSelectedRunStatus("failed");
    context.markCurrentRunStatus?.("failed", failedJobId);
    context.markCurrentSessionRunStatus("failed", failedJobId);
  }
  context.setStatus(`Error: ${payload.detail}`);
  context.addTraceEntry({
    event,
    agentId: "runtime",
    title: "Run error",
    summary: payload.detail || "Error",
    payload,
    status: "error",
  });
  if (!payload.__replay && !context.loadingArchivedRun()) {
    context.loadRuns().catch((error) => console.warn("Could not refresh runs", error));
  }
  return true;
}
