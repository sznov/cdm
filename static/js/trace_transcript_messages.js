import {
  orderedTraceEntriesForTranscript,
  traceChatMessageId,
} from "./trace_transcript_identity.js";
import { traceChatLabel } from "./trace_transcript_labels.js";
import {
  traceOutputText,
  tracePromptText,
} from "./trace_transcript_text.js";

export function isLlmOutputTraceEntry(entry = {}) {
  const event = String(entry.event || "");
  if (!String(traceOutputText(entry)).trim()) return false;
  if (event === "input_prompt") return false;
  if (event === "question_chat_done") return false;
  if (event.endsWith("_model_call_error")) return true;
  if (event.endsWith("_generation_done") || event.endsWith("_generation_start")) return true;
  if (event.endsWith("_done") && /(model|critic|planner|patch|repair|question|generation|one_shot)/i.test(event)) return true;
  if (entry.status === "streaming" && /(generation|model|critic|planner|patch|repair|question|one_shot)/i.test(event)) return true;
  return false;
}

export function traceTranscriptMessagesForEntry(entry, traceEntries = []) {
  const messages = [];
  if (entry?.event === "input_prompt") {
    const prompt = tracePromptText(entry);
    if (String(prompt).trim()) {
      messages.push({
        id: traceChatMessageId(entry, "prompt", traceEntries),
        role: "user",
        label: traceChatLabel(entry, "prompt"),
        timestampUtc: entry.timestamp_utc || "",
        completedTimestampUtc: entry.completed_at_utc || "",
        timingKind: "event",
        text: prompt,
        pre: true,
        markdown: false,
        collapsed: true,
      });
    }
  }
  if (isLlmOutputTraceEntry(entry)) {
    const streaming = entry.status === "streaming";
    messages.push({
      id: traceChatMessageId(entry, "output", traceEntries),
      role: "assistant",
      label: streaming ? `Current output · ${traceChatLabel(entry, "output")}` : traceChatLabel(entry, "output"),
      timestampUtc: entry.timestamp_utc || "",
      completedTimestampUtc: entry.completed_at_utc || "",
      timingKind: "interval",
      text: traceOutputText(entry),
      pre: true,
      markdown: false,
      collapsed: !streaming,
    });
  }
  return messages;
}

export function traceTranscriptMessages(traceEntries = []) {
  return orderedTraceEntriesForTranscript(traceEntries).flatMap((entry) => traceTranscriptMessagesForEntry(entry, traceEntries));
}
