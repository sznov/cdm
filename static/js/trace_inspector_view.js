import {
  formatJson,
  formatLocalTime,
} from './format.js';
import { traceIconSvg } from './icons.js';

function detailBlock(title, value) {
  const block = document.createElement("div");
  block.className = "detail-block";
  block.dataset.detailTitle = title;
  const heading = document.createElement("h4");
  heading.textContent = title;
  const pre = document.createElement("pre");
  pre.textContent = typeof value === "string" ? value : formatJson(value);
  block.append(heading, pre);
  return block;
}

export function traceInspectorDetailPre(elements = {}, title = "") {
  if (!elements.traceInspector) return null;
  for (const block of elements.traceInspector.querySelectorAll(".detail-block")) {
    const heading = block.querySelector("h4");
    if (block.dataset.detailTitle === title || heading?.textContent === title) {
      return block.querySelector("pre");
    }
  }
  return null;
}

export function updateTraceInspectorDetailView(options = {}) {
  let pre = traceInspectorDetailPre(options.elements || {}, options.title || "");
  if (!pre) {
    options.renderTraceInspector?.();
    pre = traceInspectorDetailPre(options.elements || {}, options.title || "");
  }
  if (!pre) return false;
  const value = typeof options.value === "string" ? options.value : formatJson(options.value);
  options.setScrollableText?.(pre, value);
  return true;
}

function appendInspectorActions(container, actions = []) {
  const actionsNode = document.createElement("div");
  actionsNode.className = "trace-inspector-actions";
  for (const action of actions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "trace-icon-action";
    const icon = traceIconSvg(action.label);
    if (icon) {
      button.classList.add(`trace-icon-${action.label}`);
      button.innerHTML = icon;
    } else {
      button.textContent = action.label;
    }
    button.title = action.title;
    button.setAttribute("aria-label", action.title);
    button.disabled = Boolean(action.disabled);
    button.addEventListener("click", action.handler);
    actionsNode.append(button);
  }
  container.append(actionsNode);
}

export function renderTraceInspectorView(options = {}) {
  const elements = options.elements || {};
  if (!elements.traceInspector) return false;
  if (elements.jumpToCurrent) {
    const latest = options.latestEntry || null;
    const alreadyFollowing = Boolean(latest && options.autoFollowTrace && options.selectedTraceId === latest.id);
    elements.jumpToCurrent.disabled = !latest || alreadyFollowing;
    elements.jumpToCurrent.classList.toggle("is-following", alreadyFollowing);
    elements.jumpToCurrent.innerHTML = traceIconSvg("up");
    elements.jumpToCurrent.setAttribute("aria-label", alreadyFollowing ? "Already following current" : "Jump to current");
    elements.jumpToCurrent.title = alreadyFollowing ? "Already following current" : "Jump to current";
  }
  elements.traceInspector.innerHTML = "";
  const entry = (options.traceEntries || []).find((candidate) => candidate.id === options.selectedTraceId);
  if (!entry) {
    if (elements.traceInspectorTitle) elements.traceInspectorTitle.textContent = "Select a trace row";
    return true;
  }
  if (elements.traceInspectorTitle) elements.traceInspectorTitle.textContent = entry.title;
  const summary = document.createElement("p");
  summary.textContent = `${entry.agent_name} | ${entry.event} | ${formatLocalTime(entry.created_at)} local | ${entry.created_at} UTC`;
  elements.traceInspector.append(summary);
  appendInspectorActions(elements.traceInspector, options.actions || []);
  if (entry.output) elements.traceInspector.append(detailBlock("Model Output", entry.output));
  return true;
}
