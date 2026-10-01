import {
  formatModelOutputForDisplay,
  markdownToHtml,
} from "./format.js";
import {
  maybeFollowChat,
  shouldFollowChat,
} from "./chat_scroll.js";
import { setChatMessageCollapsed } from "./chat_message_collapse.js";

export function updateChatMessage(container, row, text, options = {}) {
  if (!row) return null;
  const follow = options.follow ?? (!options.renderingTranscript && shouldFollowChat(container));
  row.dataset.text = text || "";
  const role = row.dataset.role || "";
  const displayText = options.pre ? String(text || "") : role === "user" ? String(text || "") : formatModelOutputForDisplay(text);
  if (options.label) {
    const label = row.querySelector(".chat-message-header strong");
    if (label) label.textContent = options.label;
  }
  const body = row.querySelector(".chat-message-body");
  if (body) {
    body.classList.toggle("chat-message-markdown", Boolean(options.markdown));
    if (options.markdown) body.innerHTML = markdownToHtml(displayText);
    else body.textContent = displayText;
  }
  if (options.collapsed !== undefined) setChatMessageCollapsed(row, Boolean(options.collapsed));
  else setChatMessageCollapsed(row, row.classList.contains("is-collapsed"));
  maybeFollowChat(container, follow);
  return row;
}
