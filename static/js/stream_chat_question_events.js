export function handleQuestionChatEvent(context, event, payload) {
  if (event === "question_chat_start") {
    if (payload.question) context.appendQuestionChatMessage("user", payload.question, { dedupeAny: true });
    context.setStatus(payload.summary || "Question submitted.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "modelQuestionAnswerer",
      title: "Question submitted",
      summary: payload.summary || payload.question || "Read-only model question submitted.",
      output: payload.question || "",
      payload,
      status: "running",
    });
    context.updateQuestionChatControls();
    return true;
  }
  if (event === "question_generation_start") {
    context.setStatus(payload.summary || "Generating answer...");
    context.startCurrentGenerationStream({
      event,
      agentId: payload.agent_id || "modelQuestionAnswerer",
      title: "Question model call",
      summary: payload.summary || "Streaming question answer.",
      payload,
    });
    return true;
  }
  if (event === "question_generation_delta") {
    if (!context.currentGenerationTraceId()) {
      context.startCurrentGenerationStream({
        event: "question_generation_start",
        agentId: payload.agent_id || "modelQuestionAnswerer",
        title: "Question model call",
        summary: "Streaming question answer.",
        payload,
      });
    }
    context.appendCurrentGeneration(payload.delta || "");
    return true;
  }
  if (event === "question_model_call_error") {
    context.appendQuestionChatMessage("assistant", payload.summary || payload.error || "Question model call failed.", {
      dedupe: true,
    });
    context.setStatus(payload.summary || "Question model call failed.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "modelQuestionAnswerer",
      title: "Question failed",
      summary: payload.summary || payload.error || "",
      output: payload.error || "",
      payload,
      status: "rejected",
    });
    context.updateQuestionChatControls();
    return true;
  }
  if (event === "question_generation_done") {
    const output = context.completeCurrentGenerationStream({
      event,
      payload,
      clearTraceId: true,
      makePatch: (rawOutput) => ({
        event,
        payload,
        summary: payload.summary || "Question model call completed.",
        rawOutput,
        status: "done",
        tags: ["model_output"],
      }),
      makeFallbackEntry: (rawOutput) => ({
        event,
        agentId: payload.agent_id || "modelQuestionAnswerer",
        title: "Question model call",
        summary: payload.summary || "Question model call completed.",
        rawOutput,
        payload,
        status: "done",
      }),
    });
    if (payload.answer) context.appendQuestionChatMessage("assistant", payload.answer, { dedupe: true });
    context.setStatus(payload.summary || "Question model call completed.");
    context.setCurrentGenerationOutput(output);
    return true;
  }
  if (event === "question_chat_done") {
    if (payload.error) context.appendQuestionChatMessage("assistant", payload.summary || payload.error, { dedupe: true });
    context.setStatus(payload.summary || "Question answered.");
    context.addTraceEntry({
      event,
      agentId: "modelQuestionAnswerer",
      title: "Question answered",
      summary: payload.summary || "Question answered.",
      output: payload.answer || payload.error || "",
      payload,
      status: payload.error ? "rejected" : "accepted",
    });
    context.updateQuestionChatControls();
    return true;
  }
  return false;
}
