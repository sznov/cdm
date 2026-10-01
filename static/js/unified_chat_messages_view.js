import { els } from "./dom.js";
import {
  appendChatMessage,
  transcriptScrollTopForElement as chatTranscriptScrollTopForElement,
  toggleChatMessageCollapsed,
  updateChatMessage,
} from "./chat_messages.js";
import {
  appendSideChatMessage,
  CORRECTION_LOG_EMPTY_TEXT,
  QUESTION_LOG_EMPTY_TEXT,
} from "./side_chat_logs.js";

export function appendUnifiedChatMessageView(role, text, options = {}) {
  return appendChatMessage(els.unifiedChatLog, role, text, options);
}

export function appendCorrectionChatMessageView(kind, text, options = {}) {
  appendUnifiedChatMessageView(kind === "user" ? "user" : "assistant", text || "", options);
  appendSideChatMessage(els.correctionChatLog, kind, text, {
    ...options,
    assistantLabel: "Patch clerk",
    emptyText: CORRECTION_LOG_EMPTY_TEXT,
  });
}

export function appendQuestionChatMessageView(kind, text, options = {}) {
  appendUnifiedChatMessageView(kind === "user" ? "user" : "assistant", text || "", options);
  appendSideChatMessage(els.questionChatLog, kind, text, {
    ...options,
    assistantLabel: "LLM",
    emptyText: QUESTION_LOG_EMPTY_TEXT,
  });
}

export function transcriptScrollTopForElementView(element, topPadding = 14) {
  return chatTranscriptScrollTopForElement(els.unifiedChatLog, element, topPadding);
}

export function toggleUnifiedChatMessageCollapsedView(row) {
  toggleChatMessageCollapsed(els.unifiedChatLog, row);
}

export function updateUnifiedChatMessageView(row, text, options = {}) {
  return updateChatMessage(els.unifiedChatLog, row, text, options);
}
