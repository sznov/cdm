import {
  formatModelOutputForDisplay,
  markdownToHtml,
} from './format.js';
import { traceTranscriptMessages } from './trace_transcript.js';

let modelOutputRenderFrame = 0;

export function modelOutputTextForDisplayView(options = {}) {
  const elements = options.elements || {};
  const traceEntries = options.traceEntries || [];
  const activeTraceOutput = options.currentGenerationTraceId
    ? traceEntries.find((candidate) => candidate.id === options.currentGenerationTraceId)?.output || ""
    : "";
  const latestStreamingOutput = !activeTraceOutput
    ? [...traceEntries].reverse().find((entry) => entry.status === "streaming" && entry.output)?.output || ""
    : "";
  const output = activeTraceOutput || latestStreamingOutput || elements.rawOutput?.textContent || options.currentGenerationOutput || "";
  if (output.trim()) return formatModelOutputForDisplay(output);
  return "";
}

export function ensureModelOutputBubbleView(elements = {}) {
  if (!elements.unifiedChatLog || !elements.modelOutputMarkdown) return false;
  if (elements.modelOutputMarkdown.parentElement !== elements.unifiedChatLog) {
    elements.unifiedChatLog.prepend(elements.modelOutputMarkdown);
    return true;
  }
  if (elements.unifiedChatLog.firstElementChild !== elements.modelOutputMarkdown) {
    elements.unifiedChatLog.prepend(elements.modelOutputMarkdown);
    return true;
  }
  return false;
}

function modelOutputMarkdownBody(elements = {}) {
  return elements.modelOutputMarkdown?.querySelector(".chat-message-body") || elements.modelOutputMarkdown;
}

export function renderModelOutputMarkdownView(options = {}) {
  const elements = options.elements || {};
  if (!elements.modelOutputMarkdown) return false;
  ensureModelOutputBubbleView(elements);
  const traceEntries = options.traceEntries || [];
  if (traceTranscriptMessages(traceEntries).length) {
    elements.modelOutputMarkdown.hidden = true;
    return true;
  }
  const text = modelOutputTextForDisplayView(options);
  const hideEmptyGeneratedSummary = !text.trim() && Boolean(options.currentWorkingModel);
  elements.unifiedChatPanel?.classList.toggle("no-model-output", hideEmptyGeneratedSummary);
  elements.modelOutputMarkdown.hidden = hideEmptyGeneratedSummary;
  const body = modelOutputMarkdownBody(elements);
  if (hideEmptyGeneratedSummary) {
    elements.modelOutputMarkdown.classList.add("is-empty");
    if (body) body.textContent = "";
    return true;
  }
  elements.modelOutputMarkdown.hidden = false;
  if (!text.trim()) {
    const emptyText = options.operationPending
      ? "Waiting for model output..."
      : "Start a modeling session to see the build log.";
    elements.modelOutputMarkdown.classList.add("is-empty");
    if (body) body.textContent = emptyText;
    return true;
  }
  const formatted = formatModelOutputForDisplay(text);
  elements.modelOutputMarkdown.classList.remove("is-empty");
  if (body) body.innerHTML = markdownToHtml(formatted);
  if (options.operationPending && elements.unifiedChatLog) {
    elements.unifiedChatLog.scrollTop = elements.unifiedChatLog.scrollHeight;
  }
  return true;
}

export function scheduleModelOutputMarkdownRenderView(render) {
  if (modelOutputRenderFrame) return false;
  const schedule = typeof requestAnimationFrame === "function"
    ? requestAnimationFrame
    : (callback) => setTimeout(callback, 16);
  modelOutputRenderFrame = schedule(() => {
    modelOutputRenderFrame = 0;
    render?.();
  });
  return true;
}
