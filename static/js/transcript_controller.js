import {
  openBuildLogModalView,
  renderBuildLogModalBodyView,
  scheduleBuildLogModalRenderView,
  syncBuildLogModalCurrentOutputView,
} from './build_log_modal.js';
import {
  appendCorrectionChatMessageView,
  appendQuestionChatMessageView,
  appendUnifiedChatMessageView,
  transcriptScrollTopForElementView,
  toggleUnifiedChatMessageCollapsedView,
  updateUnifiedChatMessageView,
} from './unified_chat_view.js';
import { renderSessionChatView } from './session_chat.js';

export function appendCorrectionChatMessage(context, kind, text, options = {}) {
  appendCorrectionChatMessageView(kind, text, {
    ...options,
    renderingTranscript: context.renderingSessionTranscript(),
  });
}

export function appendQuestionChatMessage(context, kind, text, options = {}) {
  appendQuestionChatMessageView(kind, text, {
    ...options,
    renderingTranscript: context.renderingSessionTranscript(),
  });
}

export function appendUnifiedChatMessage(context, role, text, options = {}) {
  return appendUnifiedChatMessageView(role, text, {
    ...options,
    renderingTranscript: context.renderingSessionTranscript(),
  });
}

export function transcriptScrollTopForElement(element, topPadding = 14) {
  return transcriptScrollTopForElementView(element, topPadding);
}

export function toggleUnifiedChatMessageCollapsed(row) {
  toggleUnifiedChatMessageCollapsedView(row);
}

export function updateUnifiedChatMessage(context, row, text, options = {}) {
  return updateUnifiedChatMessageView(row, text, {
    ...options,
    renderingTranscript: context.renderingSessionTranscript(),
  });
}

export function syncBuildLogModalCurrentOutput(context, entry = null) {
  syncBuildLogModalCurrentOutputView({
    elements: context.elements,
    traceEntries: context.traceEntries(),
    currentGenerationTraceId: context.currentGenerationTraceId(),
    entry,
    renderBody: () => scheduleBuildLogModalBody(context),
  });
}

function scheduleBuildLogModalBody(context) {
  return scheduleBuildLogModalRenderView({
    elements: context.elements,
    renderBody: () => renderBuildLogModalBody(context),
  });
}

export function renderBuildLogModalBody(context) {
  return renderBuildLogModalBodyView({
    elements: context.elements,
    traceEntries: context.traceEntries(),
    checkpoints: context.sortedTranscriptCheckpoints(),
    createCheckpointCard: context.createTranscriptCheckpointCard,
    modelOutputText: context.modelOutputTextForDisplay(),
  });
}

export function openBuildLogModal(context, options = {}) {
  openBuildLogModalView({
    elements: context.elements,
    renderBody: () => renderBuildLogModalBody(context),
    openFallback: () => context.openTextModal("Build log", "No build log viewer is available."),
    scrollToBottom: Boolean(options.scrollToBottom),
  });
}

export function upsertCorrectionStreamChat(context, text, options = {}) {
  if (!context.activeCorrectionStreamChatId()) {
    context.setActiveCorrectionStreamChatId(`correction-stream-${Date.now()}`);
  }
  return appendUnifiedChatMessage(context, "assistant", text || "Generating correction patch operations...", {
    messageId: context.activeCorrectionStreamChatId(),
    label: options.label || "Patch clerk output",
    pre: true,
    collapsible: true,
    collapsed: Boolean(options.collapsed),
  });
}

export function renderSessionChat(context) {
  let rendered = false;
  context.setRenderingSessionTranscript(true);
  try {
    rendered = renderSessionChatView({
      elements: context.elements,
      traceEntries: context.traceEntries(),
      currentSession: context.currentSession(),
      checkpoints: context.sortedTranscriptCheckpoints(),
      ensureModelOutputBubble: context.ensureModelOutputBubble,
      appendCheckpointCard: context.appendTranscriptCheckpointCard,
    });
  } finally {
    context.setRenderingSessionTranscript(false);
  }
  if (!rendered) return;
  context.renderDecisionRail();
  context.updateDecisionOptionControls();
  context.refreshModelOutputMarkdown();
}
