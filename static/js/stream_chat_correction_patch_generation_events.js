export function handleCorrectionPatchGenerationEvent(context, event, payload) {
  if (event === "correction_patch_generation_start") {
    if (!context.activeCorrectionStreamChatId()) context.setActiveCorrectionStreamChatId(`correction-stream-${Date.now()}`);
    context.upsertCorrectionStreamChat(payload.summary || "Generating correction patch operations...");
    context.setStatus(payload.summary || "Generating correction patch operations...");
    context.startCurrentGenerationStream({
      event,
      agentId: payload.agent_id || "patchOperationClerk",
      title: "Correction patch model call",
      summary: payload.summary || "Streaming correction patch model output.",
      payload,
    });
    return true;
  }
  if (event === "correction_patch_generation_delta") {
    if (!context.currentGenerationTraceId()) {
      context.startCurrentGenerationStream({
        event: "correction_patch_generation_start",
        agentId: payload.agent_id || "patchOperationClerk",
        title: "Correction patch model call",
        summary: "Streaming correction patch model output.",
        payload,
      });
    }
    context.appendCurrentGeneration(payload.delta || "");
    context.upsertCorrectionStreamChat(context.currentGenerationOutput() || "Generating correction patch operations...");
    return true;
  }
  if (event === "correction_patch_model_call_error") {
    context.upsertCorrectionStreamChat(payload.summary || payload.error || "Correction patch model call failed.", {
      collapsed: false,
    });
    context.setActiveCorrectionStreamChatId("");
    context.appendCorrectionChatMessage("assistant", payload.summary || payload.error || "Correction patch model call failed.", { dedupe: true });
    context.setStatus(payload.summary || "Correction patch model call failed.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "patchOperationClerk",
      title: "Correction patch failed",
      summary: payload.summary || payload.error || "",
      output: payload.error || "",
      payload,
      status: "rejected",
    });
    return true;
  }
  if (event === "correction_patch_generation_done") {
    const output = context.completeCurrentGenerationStream({
      event,
      payload,
      clearTraceId: true,
      makeFallbackEntry: (rawOutput) => ({
        event,
        agentId: payload.agent_id || "patchOperationClerk",
        title: "Correction patch output",
        summary: payload.summary || "Raw structured patch output.",
        output: rawOutput,
        payload,
        status: "done",
      }),
    });
    context.upsertCorrectionStreamChat(context.currentGenerationOutput() || payload.summary || "Correction patch model call completed.", {
      collapsed: true,
    });
    context.setActiveCorrectionStreamChatId("");
    context.setStatus(payload.summary || "Correction patch model call completed.");
    context.setCurrentGenerationOutput(output);
    return true;
  }
  return false;
}
