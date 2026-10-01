import {
  markdownToHtml,
} from './format.js';
import {
  isScrolledNearBottom,
  setChatMessageCollapsed,
} from './chat_messages.js';
import {
  isLlmOutputTraceEntry,
  traceOutputText,
  traceTranscriptMessagesForEntry,
} from './trace_transcript.js';
import { buildLogModalMessageRow } from './build_log_modal_message.js';

const pendingBodyUpdates = new Map();
let pendingStructuralRender = null;
let structuralRenderFrame = 0;
let structuralSelectionListener = false;

function selectionIntersectsNode(node) {
  const selection = window.getSelection?.();
  if (!selection || selection.isCollapsed || !node?.isConnected) return false;
  for (let index = 0; index < selection.rangeCount; index += 1) {
    const range = selection.getRangeAt(index);
    try {
      if (range.intersectsNode(node)) return true;
    } catch {
      return false;
    }
  }
  return false;
}

function stableRowKey(row) {
  if (row?.dataset?.messageId) return `message:${row.dataset.messageId}`;
  if (row?.dataset?.checkpointId) return `checkpoint:${row.dataset.checkpointId}`;
  return "";
}

function captureStructuralViewState(container) {
  const containerRect = container.getBoundingClientRect();
  const rows = [...container.children];
  const anchor = rows.find((row) => row.getBoundingClientRect().bottom > containerRect.top + 1) || null;
  return {
    nearBottom: isScrolledNearBottom(container, 96),
    scrollLeft: container.scrollLeft,
    scrollTop: container.scrollTop,
    anchorKey: stableRowKey(anchor),
    anchorOffset: anchor ? anchor.getBoundingClientRect().top - containerRect.top : 0,
    collapsedByMessageId: new Map(
      rows
        .filter((row) => row.dataset?.messageId)
        .map((row) => [row.dataset.messageId, row.classList.contains("is-collapsed")]),
    ),
  };
}

function removeDuplicateStableRows(container) {
  const seen = new Set();
  for (const row of [...container.children]) {
    const key = stableRowKey(row);
    if (!key || !seen.has(key)) {
      if (key) seen.add(key);
      continue;
    }
    row.remove();
  }
}

function restoreStructuralViewState(container, viewState) {
  for (const row of container.querySelectorAll("[data-message-id]")) {
    if (!viewState.collapsedByMessageId.has(row.dataset.messageId)) continue;
    setChatMessageCollapsed(row, viewState.collapsedByMessageId.get(row.dataset.messageId));
  }
  container.scrollLeft = viewState.scrollLeft;
  if (viewState.nearBottom) {
    container.scrollTop = container.scrollHeight;
    return;
  }
  const anchor = [...container.children].find((row) => stableRowKey(row) === viewState.anchorKey);
  if (!anchor) {
    container.scrollTop = viewState.scrollTop;
    return;
  }
  const containerTop = container.getBoundingClientRect().top;
  container.scrollTop += anchor.getBoundingClientRect().top - containerTop - viewState.anchorOffset;
}

function stopStructuralSelectionListener() {
  if (!structuralSelectionListener) return;
  document.removeEventListener("selectionchange", onStructuralSelectionChange);
  structuralSelectionListener = false;
}

function requestStructuralRenderFrame() {
  if (structuralRenderFrame || !pendingStructuralRender) return;
  structuralRenderFrame = window.requestAnimationFrame(flushStructuralRender);
}

function onStructuralSelectionChange() {
  const container = pendingStructuralRender?.elements?.buildLogModalBody;
  if (container && selectionIntersectsNode(container)) return;
  stopStructuralSelectionListener();
  requestStructuralRenderFrame();
}

function flushStructuralRender() {
  structuralRenderFrame = 0;
  const pending = pendingStructuralRender;
  if (!pending) return;
  const elements = pending.elements || {};
  const container = elements.buildLogModalBody;
  if (!elements.buildLogModal?.open || !container) {
    pendingStructuralRender = null;
    stopStructuralSelectionListener();
    return;
  }
  if (selectionIntersectsNode(container)) {
    if (!structuralSelectionListener) {
      document.addEventListener("selectionchange", onStructuralSelectionChange);
      structuralSelectionListener = true;
    }
    return;
  }
  pendingStructuralRender = null;
  stopStructuralSelectionListener();
  const viewState = captureStructuralViewState(container);
  pending.renderBody?.();
  removeDuplicateStableRows(container);
  restoreStructuralViewState(container, viewState);
}

export function scheduleBuildLogModalRenderView(options = {}) {
  if (!options.elements?.buildLogModal?.open || !options.elements?.buildLogModalBody) return false;
  pendingStructuralRender = options;
  requestStructuralRenderFrame();
  return true;
}

function applyBodyContent(body, text, options = {}) {
  body.classList.toggle("chat-message-markdown", Boolean(options.markdown));
  body.classList.toggle("chat-message-pre", Boolean(options.pre));
  if (options.markdown) body.innerHTML = markdownToHtml(text);
  else body.textContent = text;
}

function flushPendingBodyUpdates() {
  for (const [body, pending] of pendingBodyUpdates) {
    if (!body.isConnected) {
      pendingBodyUpdates.delete(body);
      continue;
    }
    if (selectionIntersectsNode(body)) continue;
    applyBodyContent(body, pending.text, pending.options);
    pendingBodyUpdates.delete(body);
  }
  if (!pendingBodyUpdates.size) document.removeEventListener("selectionchange", flushPendingBodyUpdates);
}

function deferBodyContentUpdate(body, text, options = {}) {
  const shouldListen = !pendingBodyUpdates.size;
  pendingBodyUpdates.set(body, { text, options });
  if (shouldListen) document.addEventListener("selectionchange", flushPendingBodyUpdates);
}

function updateBodyContentPreservingSelection(body, text, options = {}) {
  const next = String(text || "");
  const current = body.textContent || "";
  if (current === next) {
    pendingBodyUpdates.delete(body);
    return;
  }
  if (!options.markdown && next.startsWith(current)) {
    pendingBodyUpdates.delete(body);
    body.classList.toggle("chat-message-markdown", false);
    body.classList.toggle("chat-message-pre", Boolean(options.pre));
    body.append(document.createTextNode(next.slice(current.length)));
    return;
  }
  if (selectionIntersectsNode(body)) {
    deferBodyContentUpdate(body, next, options);
    return;
  }
  pendingBodyUpdates.delete(body);
  applyBodyContent(body, next, options);
}

export function syncBuildLogModalCurrentOutputView(options = {}) {
  const elements = options.elements || {};
  if (!elements.buildLogModal?.open || !elements.buildLogModalBody) return;
  const traceEntries = options.traceEntries || [];
  const activeEntry =
    options.entry ||
    (options.currentGenerationTraceId ? traceEntries.find((candidate) => candidate.id === options.currentGenerationTraceId) : null) ||
    [...traceEntries].reverse().find((candidate) => candidate.status === "streaming" && traceOutputText(candidate));
  if (!activeEntry || !isLlmOutputTraceEntry(activeEntry)) {
    options.renderBody?.();
    return;
  }
  const message = traceTranscriptMessagesForEntry(activeEntry, traceEntries).find((candidate) => candidate.role === "assistant");
  if (!message) return;
  const modalShouldFollow = isScrolledNearBottom(elements.buildLogModalBody, 96);
  const row = buildLogModalMessageRow(elements, message.id);
  if (!row) {
    options.renderBody?.();
    if (modalShouldFollow) elements.buildLogModalBody.scrollTop = elements.buildLogModalBody.scrollHeight;
    return;
  }

  const body = row.querySelector(".chat-message-body");
  const label = row.querySelector(".chat-message-title");
  const bodyShouldFollow = body ? isScrolledNearBottom(body, 96) : true;
  row.dataset.text = message.text;
  row.dataset.role = message.role;
  if (label) label.textContent = message.label;
  if (body) {
    updateBodyContentPreservingSelection(body, message.text, {
      markdown: Boolean(message.markdown),
      pre: Boolean(message.pre),
    });
    if (bodyShouldFollow) body.scrollTop = body.scrollHeight;
  }
  if (modalShouldFollow) elements.buildLogModalBody.scrollTop = elements.buildLogModalBody.scrollHeight;
  if (activeEntry.status !== "streaming") options.renderBody?.();
}
