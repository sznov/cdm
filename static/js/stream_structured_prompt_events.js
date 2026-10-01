import {
  formatPromptPayload,
} from './format.js';

export function handleStructuredPromptEvent(context, event, payload) {
  if (event === "input_prompt") {
    if (context.elements.inputPrompt) context.elements.inputPrompt.textContent = formatPromptPayload(payload);
    const agentId = payload.agent_id || "operationAgent";
    context.addTraceEntry({
      event,
      agentId,
      title: payload.title || "Evaluated prompt",
      summary: payload.summary || "Template placeholders resolved into the prompt sent to the model.",
      prompt: formatPromptPayload(payload),
      payload,
    });
    return true;
  }
  if (event === "modeling_plan_validated") {
    context.setStatus(payload.summary || "Modeling plan validated.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "planValidator",
      title: "Modeling plan validated",
      summary: payload.summary || "Planner output parsed into a checklist.",
      payload,
      status: payload.status === "fallback_after_invalid_plan" ? "rejected" : "accepted",
    });
    return true;
  }
  return false;
}
