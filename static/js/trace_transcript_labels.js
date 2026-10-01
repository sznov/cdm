import { traceStepKey } from "./trace_transcript_identity.js";

const TRACE_CHAT_LABELS = {
  initial: { prompt: "Initial prompt", output: "Initial response" },
  naming: { prompt: "Naming prompt", output: "Naming response" },
  review: { prompt: "Review prompt", output: "Review response" },
  revision: { prompt: "Revision prompt", output: "Revision response" },
  final: { prompt: "Final correction prompt", output: "Final correction response" },
  question: { prompt: "Question prompt", output: "Answer" },
  full: { prompt: "Full-model prompt", output: "Full-model response" },
  model: { prompt: "Model prompt", output: "Model response" },
};

export function traceChatLabel(entry = {}, kind = "output") {
  const key = traceStepKey(entry);
  return TRACE_CHAT_LABELS[key]?.[kind] || TRACE_CHAT_LABELS.model[kind];
}
