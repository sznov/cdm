import { appendChatMessage } from './chat_messages.js';
import {
  orderedTraceEntriesForTranscript,
  traceTranscriptMessagesForEntry,
} from './trace_transcript.js';

export function appendTranscriptChatMessage(elements, role, text, options = {}) {
  return appendChatMessage(elements.unifiedChatLog, role, text, {
    ...options,
    renderingTranscript: true,
  });
}

export function appendTraceTranscriptEntry(options = {}, entry, checkpointsByEntry, appendedCheckpoints) {
  const elements = options.elements || {};
  const traceEntries = options.traceEntries || [];
  const entryCheckpoints = checkpointsByEntry.get(entry.id) || [];
  for (const message of traceTranscriptMessagesForEntry(entry, traceEntries)) {
    appendTranscriptChatMessage(elements, message.role, message.text, {
      messageId: message.id,
      label: message.label,
      markdown: Boolean(message.markdown),
      pre: Boolean(message.pre),
      collapsible: true,
      collapsed: message.collapsed ?? true,
      follow: false,
    });
  }
  for (const checkpoint of entryCheckpoints) {
    options.appendCheckpointCard?.(checkpoint);
    appendedCheckpoints.add(checkpoint.id);
  }
}

export function orderedSessionTraceEntries(traceEntries = []) {
  return orderedTraceEntriesForTranscript(traceEntries);
}
