export function handleCorrectionPatchChatLifecycleEvent(context, event, payload) {
  if (event === "correction_patch_chat_start") {
    if (payload.user_message) context.appendCorrectionChatMessage("user", payload.user_message, { dedupeAny: true });
    context.setStatus(payload.summary || "Correction patch chat started.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "patchOperationClerk",
      title: "Correction submitted",
      summary: payload.summary || "Free-form correction submitted.",
      output: payload.user_message || "",
      payload,
      status: "running",
    });
    return true;
  }
  if (event === "correction_patch_chat_progress") {
    context.appendCorrectionChatMessage("assistant", payload.summary || "Correction patch operations applied.", {
      dedupe: true,
    });
    context.setStatus(payload.summary || "Correction patch operations applied.");
    context.addTraceEntry({
      event,
      agentId: "incrementalOpApplier",
      title: "Correction progress",
      summary: payload.summary || "",
      payload,
      status: payload.rejected_count ? "rejected" : "accepted",
    });
    return true;
  }
  if (event === "correction_patch_chat_done") {
    if (payload.decision_patches) context.updateDecisionPatches(payload.decision_patches);
    context.appendCorrectionChatMessage("assistant", payload.summary || "Correction patch chat complete.", { dedupe: true });
    context.setStatus(payload.summary || "Correction patch chat complete.");
    context.addTraceEntry({
      event,
      agentId: "incrementalOpApplier",
      title: "Correction complete",
      summary: payload.summary || "",
      payload,
      status: payload.rejected_count ? "rejected" : "accepted",
    });
    context.updateCorrectionChatControls();
    return true;
  }
  return false;
}
