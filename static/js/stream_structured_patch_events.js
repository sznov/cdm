import {
  formatJson,
} from './format.js';

export function handleStructuredPatchEvent(context, event, payload) {
  if (event === "operation_batch_raw") {
    const output = payload.raw_output || "";
    context.setCurrentGenerationOutput(output);
    context.setScrollableText(context.elements.rawOutput, output);
    context.setStatus(`Iteration ${payload.iteration}, attempt ${payload.batch_attempt}: received operation output.`);
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "operationAgent",
      title: `Raw operation output ${payload.iteration}.${payload.batch_attempt}`,
      summary: "Raw model output before validation.",
      output,
      payload,
    });
    return true;
  }
  if (event === "model_generation_interrupted") {
    context.setCurrentGenerationOutput(payload.raw_output || payload.partial_output || context.currentGenerationOutput());
    context.markCurrentGenerationInterrupted(payload);
    context.setStatus(payload.detail || "Generation interrupted; partial output preserved.");
    return true;
  }
  if (event === "structured_patch_operation_candidate") {
    context.setStatus(payload.summary || "Structured patch operation candidate parsed.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "patchOperationClerk",
      title: `Patch op candidate ${payload.sequence || ""}`.trim(),
      summary: payload.summary || "",
      output: payload.operation ? formatJson(payload.operation) : "",
      payload,
      status: "candidate",
    });
    return true;
  }
  if (event === "structured_patch_operation_applied") {
    const status = payload.status || payload.result?.status || "";
    const titleStatus =
      status === "accepted"
        ? "accepted"
        : status === "deferred"
        ? "deferred"
        : status === "already_satisfied"
        ? "already satisfied"
        : "rejected";
    context.setStatus(payload.summary || `Structured patch operation ${titleStatus}.`);
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "incrementalOpApplier",
      title: `Patch op ${titleStatus}`,
      summary: payload.summary || payload.result?.reason || "",
      output: payload.result ? formatJson(payload.result) : "",
      payload,
      status: status || "accepted",
    });
    return true;
  }
  if (event === "structured_patch_operation_parse_error") {
    context.setStatus(payload.summary || payload.error || "Structured patch operation parse error.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "patchOperationClerk",
      title: "Patch op parse error",
      summary: payload.summary || payload.error || "",
      payload,
      status: "rejected",
    });
    return true;
  }
  return false;
}
