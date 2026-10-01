import {
  formatModelOutputForDisplay,
  markdownToHtml,
} from "./format.js";
import {
  maybeFollowChat,
  shouldFollowChat,
} from "./chat_scroll.js";
import {
  setChatMessageCollapsed,
  toggleChatMessageCollapsed,
  updateChatMessageToggleIcon,
} from "./chat_message_collapse.js";
import { updateChatMessage } from "./chat_message_update.js";
import { createBuildLogTimeElement } from "./build_log_timing.js";

export function appendChatMessage(container, role, text, options = {}) {
  if (!container || !String(text || "").trim()) return null;
  const follow = options.follow ?? (!options.renderingTranscript && shouldFollowChat(container));
  if (options.messageId) {
    const existing = [...container.children].find(
      (candidate) => candidate?.dataset?.messageId === options.messageId
    );
    if (existing) {
      updateChatMessage(container, existing, text, options);
      return existing;
    }
  }
  if (options.dedupe) {
    const last = container.lastElementChild;
    if (last?.dataset?.role === role && last?.dataset?.text === text) return last;
  }
  if (options.dedupeAny) {
    const existing = [...container.children].some(
      (candidate) => candidate?.dataset?.role === role && candidate?.dataset?.text === text
    );
    if (existing) return null;
  }
  const displayText = options.pre ? String(text || "") : role === "user" ? String(text || "") : formatModelOutputForDisplay(text);
  const row = document.createElement("div");
  row.className = `chat-message build-log-row ${role}`;
  row.dataset.role = role;
  row.dataset.text = text;
  if (options.messageId) row.dataset.messageId = options.messageId;
  const header = document.createElement("div");
  header.className = "chat-message-header";
  const label = document.createElement("strong");
  label.className = "chat-message-title";
  label.textContent = options.label || (role === "user" ? "You" : "LLM");
  header.append(label);
  if (options.timestampUtc) {
    const timing = createBuildLogTimeElement(options.timestampUtc, options.completedTimestampUtc, {
      kind: options.timingKind,
    });
    if (timing) header.append(timing);
  }
  if (options.collapsible) {
    header.classList.add("is-clickable");
    header.setAttribute("role", "button");
    header.setAttribute("tabindex", "0");
    header.title = "Collapse or expand this message";
    const toggleMessage = () => toggleChatMessageCollapsed(container, row);
    header.addEventListener("click", (event) => {
      if (event.target.closest(".chat-message-toggle")) return;
      toggleMessage();
    });
    header.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      toggleMessage();
    });
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "chat-message-toggle";
    toggle.title = "Collapse or expand this message";
    updateChatMessageToggleIcon(toggle, !options.collapsed);
    toggle.addEventListener("click", toggleMessage);
    toggle.setAttribute("aria-expanded", String(!options.collapsed));
    header.append(toggle);
  }
  const body = document.createElement(options.pre ? "pre" : "div");
  body.className = `chat-message-body${options.pre ? " chat-message-pre" : ""}${options.markdown ? " chat-message-markdown" : ""}`;
  if (options.markdown) body.innerHTML = markdownToHtml(displayText);
  else body.textContent = displayText;
  row.append(header, body);
  setChatMessageCollapsed(row, Boolean(options.collapsed));
  container.append(row);
  maybeFollowChat(container, follow);
  return row;
}
