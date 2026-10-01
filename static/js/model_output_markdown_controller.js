import {
  ensureModelOutputBubbleView,
  modelOutputTextForDisplayView,
  renderModelOutputMarkdownView,
  scheduleModelOutputMarkdownRenderView,
} from "./model_output.js";
import { runActionBlocked } from './state.js';

export function modelOutputTextForDisplay(context) {
  return modelOutputTextForDisplayView({
    elements: context.elements,
    traceEntries: context.traceEntries(),
    currentGenerationTraceId: context.currentGenerationTraceId(),
    currentGenerationOutput: context.currentGenerationOutput(),
  });
}

export function ensureModelOutputBubble(context) {
  ensureModelOutputBubbleView(context.elements);
}

export function upsertTraceEntryChatBubble(context, entry) {
  if (!context.elements.unifiedChatLog || !entry) return;
  context.renderSessionChat();
}

export function renderModelOutputMarkdown(context) {
  renderModelOutputMarkdownView({
    elements: context.elements,
    traceEntries: context.traceEntries(),
    currentGenerationTraceId: context.currentGenerationTraceId(),
    currentGenerationOutput: context.currentGenerationOutput(),
    currentWorkingModel: context.currentWorkingModel(),
    operationPending: runActionBlocked(context.selectedRunId?.()),
  });
}

export function refreshModelOutputMarkdown(context) {
  renderModelOutputMarkdown(context);
  setTimeout(() => renderModelOutputMarkdown(context), 0);
  setTimeout(() => renderModelOutputMarkdown(context), 120);
}

export function scheduleModelOutputMarkdownRender(context) {
  if (!context.elements.modelOutputMarkdown) return;
  scheduleModelOutputMarkdownRenderView(() => renderModelOutputMarkdown(context));
}
