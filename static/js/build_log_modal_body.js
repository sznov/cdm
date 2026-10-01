import { formatModelOutputForDisplay } from './format.js';
import {
  orderedTraceEntriesForTranscript,
  traceTranscriptMessagesForEntry,
} from './trace_transcript.js';
import { checkpointRowsByTraceEntry } from './transcript_checkpoints.js';
import { appendBuildLogModalMessage } from './build_log_modal_message.js';

export function renderBuildLogModalBodyView(options = {}) {
  const elements = options.elements || {};
  const container = elements.buildLogModalBody;
  if (!container) return false;
  const traceEntries = options.traceEntries || [];
  container.innerHTML = "";
  const checkpoints = checkpointRowsByTraceEntry(options.checkpoints || []);
  let rendered = 0;
  for (const entry of orderedTraceEntriesForTranscript(traceEntries)) {
    const entryCheckpoints = checkpoints.get(entry.id) || [];
    for (const message of traceTranscriptMessagesForEntry(entry, traceEntries)) {
      const node = appendBuildLogModalMessage(container, message.role, message.text, {
        messageId: `modal-${message.id}`,
        label: message.label,
        timestampUtc: message.timestampUtc,
        completedTimestampUtc: message.completedTimestampUtc,
        timingKind: message.timingKind,
        markdown: Boolean(message.markdown),
        pre: Boolean(message.pre),
        collapsible: true,
        collapsed: message.collapsed ?? true,
      });
      if (node) rendered += 1;
    }
    for (const checkpoint of entryCheckpoints) {
      const card = options.createCheckpointCard?.(checkpoint, { showTiming: true });
      if (card) {
        container.append(card);
        rendered += 1;
      }
    }
  }
  if (!rendered) {
    const output = options.modelOutputText || "";
    appendBuildLogModalMessage(container, "assistant", output.trim() ? formatModelOutputForDisplay(output) : "No log output is available for this run yet.", {
      label: output.trim() ? "Current output" : "Build log",
      markdown: Boolean(output.trim()),
      collapsible: Boolean(output.trim()),
      collapsed: false,
    });
  }
  return true;
}
