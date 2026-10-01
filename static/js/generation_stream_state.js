import { traceEventTimestamp } from "./format.js";

export function startGenerationStream(context, options = {}) {
  const {
    event,
    payload = {},
    agentId,
    title,
    summary,
  } = options;
  context.setOutput("");
  context.setScrollableText(context.elements.rawOutput, "", { follow: true });
  context.setTraceId(context.addTraceEntry({
    event,
    agentId,
    title,
    summary,
    payload,
    status: "streaming",
  }));
}

export function appendGenerationDelta(context, delta) {
  const chunk = delta || "";
  context.setOutput(`${context.getOutput()}${chunk}`);
  context.appendText(context.elements.rawOutput, chunk);
  const traceId = context.getTraceId();
  if (!traceId) return;
  const entry = context.traceEntries.find((candidate) => candidate.id === traceId);
  if (entry) entry.output = `${entry.output || ""}${chunk}`;
  if (entry) context.upsertTraceEntryChatBubble(entry);
  context.scheduleModelOutputMarkdownRender();
  if (context.getSelectedTraceId() === traceId) {
    context.updateTraceInspectorDetail("Model Output", entry?.output || "");
  }
}

export function appendReplayedGenerationDelta(context, delta) {
  if (!delta) return;
  const output = `${context.getOutput()}${delta}`;
  context.setOutput(output);
  context.setScrollableText(context.elements.rawOutput, output);
  let entry = context.getTraceId()
    ? context.traceEntries.find((candidate) => candidate.id === context.getTraceId())
    : null;
  if (!entry) {
    entry = [...context.traceEntries].reverse().find((candidate) => candidate.status === "streaming");
    if (entry) context.setTraceId(entry.id);
  }
  if (entry) entry.output = `${entry.output || ""}${delta}`;
}

export function completeGenerationStream(context, options = {}) {
  const {
    event,
    payload = {},
    clearTraceId = false,
    makePatch,
    makeFallbackEntry,
  } = options;
  const output = payload.raw_output || context.getOutput();
  context.setOutput(output);
  context.setScrollableText(context.elements.rawOutput, output);
  const traceId = context.getTraceId();
  if (traceId) {
    const patch = makePatch ? makePatch(output) : {
      event,
      output: payload.raw_output || output,
      payload,
      status: "done",
    };
    context.updateTraceEntry(traceId, {
      ...patch,
      completed_at_utc: traceEventTimestamp(payload),
    });
  } else if (makeFallbackEntry) {
    context.addTraceEntry(makeFallbackEntry(output));
  }
  if (clearTraceId) context.setTraceId(null);
  return output;
}

export function markGenerationInterrupted(context, payload = {}) {
  const traceId = context.getTraceId();
  const output = context.getOutput();
  if (!traceId && !output) return;
  const partialOutput = payload.raw_output || payload.partial_output || output || "";
  const interruptedPayload = {
    ...payload,
    partial_output: partialOutput,
    raw_output: partialOutput,
  };
  if (traceId) {
    context.updateTraceEntry(traceId, {
      event: "model_generation_interrupted",
      output: partialOutput,
      payload: interruptedPayload,
      status: "interrupted",
      summary: payload.detail || "Generation interrupted; partial output preserved.",
      completed_at_utc: traceEventTimestamp(payload),
    });
  } else {
    context.addTraceEntry({
      event: "model_generation_interrupted",
      agentId: payload.agent_id || "runtime",
      title: "Generation interrupted",
      summary: payload.detail || "Generation interrupted; partial output preserved.",
      output: partialOutput,
      payload: interruptedPayload,
      status: "interrupted",
    });
  }
  context.setOutput(partialOutput);
  context.setScrollableText(context.elements.rawOutput, partialOutput);
  context.setTraceId(null);
}
