export function traceChatMessageId(entry, kind, traceEntries = []) {
  const index = Number.isInteger(entry?.trace_index) ? entry.trace_index : traceEntries.indexOf(entry);
  return `trace-${index}-${kind}`;
}

export function traceEntrySortValue(entry, traceEntries = []) {
  return Number.isInteger(entry?.trace_index) ? entry.trace_index : traceEntries.indexOf(entry);
}

export function traceStepKey(entry = {}) {
  const text = [
    entry.event,
    entry.title,
    entry.payload?.title,
    entry.agent_id,
    entry.agent_name,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
    .replace(/\basync[-_\s]*op[-_\s]*patch\b/g, " ")
    .replace(/\basync[-_\s]*patch\b/g, " ");
  if (text.includes("question")) return "question";
  if (text.includes("guarded") || text.includes("posthoc") || text.includes("post-hoc")) return "final";
  if (text.includes("draft") || text.includes("modeler")) return "initial";
  if (text.includes("coverage") || text.includes("critic") || text.includes("review")) return "review";
  if (text.includes("language") || text.includes("repair") || text.includes("name")) return "naming";
  if (text.includes("patch") || text.includes("operation") || text.includes("revision")) return "revision";
  if (text.includes("one_shot") || text.includes("one-shot") || text.includes("gold scaffold")) return "full";
  return "model";
}

export function isQuestionTraceEntry(entry = {}) {
  return traceStepKey(entry) === "question";
}

export function orderedTraceEntriesForTranscript(traceEntries = []) {
  const sortedEntries = [...traceEntries].sort((a, b) => traceEntrySortValue(a, traceEntries) - traceEntrySortValue(b, traceEntries));
  return [
    ...sortedEntries.filter((entry) => !isQuestionTraceEntry(entry)),
    ...sortedEntries.filter(isQuestionTraceEntry),
  ];
}
