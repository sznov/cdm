import { shouldFollowChat } from './chat_messages.js';
import { isPosthocTraceEvent } from './progress_checkpoints.js';
import { sessionChatRenderOptions } from './session_chat_options.js';
import {
  appendTraceTranscriptEntry,
  appendTranscriptChatMessage,
  orderedSessionTraceEntries,
} from './session_chat_trace.js';
import { checkpointRowsByTraceEntry } from './transcript_checkpoints.js';
import {
  isQuestionTraceEntry,
  traceTranscriptMessages,
  traceTranscriptMessagesForEntry,
} from './trace_transcript.js';

export { sessionChatRenderOptions } from './session_chat_options.js';

export function renderSessionChatView(options = {}) {
  const elements = options.elements || {};
  const log = elements.unifiedChatLog;
  if (!log) return false;
  const traceEntries = options.traceEntries || [];
  const checkpoints = options.checkpoints || [];
  const follow = shouldFollowChat(log);
  const previousScrollTop = log.scrollTop;
  options.ensureModelOutputBubble?.();
  for (const child of [...log.children]) {
    if (child !== elements.modelOutputMarkdown) child.remove();
  }

  const checkpointsByEntry = checkpointRowsByTraceEntry(checkpoints);
  const appendedCheckpoints = new Set();
  const appendTraceEntry = (entry) => {
    appendTraceTranscriptEntry(options, entry, checkpointsByEntry, appendedCheckpoints);
  };

  const orderedEntries = orderedSessionTraceEntries(traceEntries);
  const questionEntries = orderedEntries.filter(isQuestionTraceEntry);
  const regularEntries = orderedEntries.filter((entry) => !isQuestionTraceEntry(entry));
  const hasQuestionTraceTranscript = questionEntries.some(
    (entry) => traceTranscriptMessagesForEntry(entry, traceEntries).length > 0
  );
  const hasCorrectionTraceTranscript = traceEntries.some(isPosthocTraceEvent);
  for (const entry of regularEntries) appendTraceEntry(entry);
  for (const checkpoint of checkpoints) {
    if (appendedCheckpoints.has(checkpoint.id)) continue;
    options.appendCheckpointCard?.(checkpoint);
    appendedCheckpoints.add(checkpoint.id);
  }

  const hasTraceTranscript = traceTranscriptMessages(traceEntries).length > 0;
  const messages = options.currentSession?.chat_messages || [];
  for (const message of messages) {
    if (hasTraceTranscript && message.kind === "correction_model_output") continue;
    if (hasCorrectionTraceTranscript && message.kind === "correction") continue;
    if (hasQuestionTraceTranscript && message.kind === "question") continue;
    const role = message.role === "user" ? "user" : "assistant";
    appendTranscriptChatMessage(elements, role, message.content || "", {
      ...sessionChatRenderOptions(message, role),
      collapsible: true,
      collapsed: true,
      follow: false,
    });
  }
  for (const entry of questionEntries) appendTraceEntry(entry);

  if (follow) {
    log.scrollTop = log.scrollHeight;
  } else {
    const maxScrollTop = Math.max(0, log.scrollHeight - log.clientHeight);
    log.scrollTop = Math.min(previousScrollTop, maxScrollTop);
  }
  return true;
}
