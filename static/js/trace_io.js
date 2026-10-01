import {
  formatJson,
  formatModelOutputForDisplay,
  modelInputTextFromPayload,
} from "./format.js";
import {
  isModelCallTraceEvent,
  isTerminalTraceEntry,
} from "./trace_status.js";

export function modelInputForTraceEntry(entry, traceEntries = []) {
  const directInput = modelInputTextFromPayload(entry?.payload) || entry?.prompt || "";
  if (directInput) return directInput;
  if (!isModelCallTraceEvent(entry)) return "";
  const entryIndex = traceEntries.findIndex((candidate) => candidate.id === entry?.id);
  const agentId = entry?.agent_id || entry?.payload?.agent_id || "";
  for (let index = entryIndex - 1; index >= 0; index -= 1) {
    const candidate = traceEntries[index];
    if (!candidate) continue;
    if (candidate.event !== "input_prompt") continue;
    const candidateAgentId = candidate.agent_id || candidate.payload?.agent_id || "";
    if (agentId && candidateAgentId && candidateAgentId !== agentId) continue;
    const candidateInput = modelInputTextFromPayload(candidate.payload) || candidate.prompt || "";
    if (candidateInput) return candidateInput;
  }
  return "";
}

export function promptArtifactForTraceEntry(entry) {
  return modelInputTextFromPayload(entry?.payload) || entry?.prompt || "";
}

export function stepInputForTraceEntry(entry, options = {}) {
  if (!entry) return "";
  if (isTerminalTraceEntry(entry)) return "";
  if (entry.event === "input_prompt") {
    const parts = [
      `Prompt preparation step for ${entry.agent_name || entry.payload?.agent_id || "agent"}.`,
      entry.summary ? `STEP CONTEXT\n${entry.summary}` : "",
    ];
    const spec = String(options.specification || "").trim();
    if (spec) parts.push(`SPECIFICATION / SOURCE CONTEXT\n${spec}`);
    parts.push("The evaluated prompt produced by this step is available under Output.");
    return parts.filter(Boolean).join("\n\n---\n\n");
  }
  if (isModelCallTraceEvent(entry)) return modelInputForTraceEntry(entry, options.traceEntries || []);
  if (entry.event === "start" && entry.payload) {
    return formatJson(entry.payload);
  }
  const payload = entry.payload || {};
  for (const key of [
    "input",
    "model_input",
    "operation",
    "operations",
    "candidate",
    "finding",
    "request",
    "current_model",
    "model",
    "model_snapshot",
    "structured_model",
    "working_model",
    "resume_state",
  ]) {
    if (payload[key] != null) return typeof payload[key] === "string" ? payload[key] : formatJson(payload[key]);
  }
  return "";
}

export function stepOutputForTraceEntry(entry) {
  if (!entry) return "";
  if (entry.event === "input_prompt") return promptArtifactForTraceEntry(entry);
  if (entry.output) return formatModelOutputForDisplay(entry.output);
  const payload = entry.payload || {};
  if (entry.event === "start" && payload.job_id) return `Run created: ${payload.job_id}`;
  for (const key of [
    "structured_model",
    "model_snapshot",
    "working_model",
    "model",
    "result",
    "applied",
    "accepted",
    "rejected",
    "feedback",
    "errors",
    "issues",
    "decision_patches",
    "language_repair",
    "patches",
    "plantuml",
    "plantuml_url",
    "checkpoint_path",
    "path",
    "log_path",
    "message",
  ]) {
    if (payload[key] == null || typeof payload[key] === "boolean") continue;
    return typeof payload[key] === "string" ? payload[key] : formatJson(payload[key]);
  }
  return "";
}

export function traceEntryHasInputOrOutput(entry, options = {}) {
  return Boolean(stepInputForTraceEntry(entry, options) || stepOutputForTraceEntry(entry));
}
