import { traceIconSvg } from "./icons.js";
import { transcriptScrollTopForElement } from "./chat_scroll.js";

export function updateChatMessageToggleIcon(toggle, expanded) {
  if (!toggle) return;
  toggle.innerHTML = traceIconSvg(expanded ? "chevron-up" : "chevron-down");
  toggle.setAttribute("aria-label", expanded ? "Collapse message" : "Expand message");
}

export function setChatMessageCollapsed(row, collapsed) {
  if (!row) return;
  row.classList.toggle("is-collapsed", Boolean(collapsed));
  const expanded = !row.classList.contains("is-collapsed");
  const header = row.querySelector(".chat-message-header");
  if (header) header.setAttribute("aria-expanded", String(expanded));
  const toggle = row.querySelector(".chat-message-toggle");
  if (toggle) {
    updateChatMessageToggleIcon(toggle, expanded);
    toggle.setAttribute("aria-expanded", String(expanded));
  }
}

export function toggleChatMessageCollapsed(container, row) {
  if (!row) return;
  const collapsing = !row.classList.contains("is-collapsed");
  const targetScrollTop = transcriptScrollTopForElement(container, row);
  const shouldAnchorToCollapsedTitle = Boolean(container && collapsing && container.scrollTop >= targetScrollTop - 6);
  setChatMessageCollapsed(row, collapsing);
  if (shouldAnchorToCollapsedTitle) {
    container.scrollTop = targetScrollTop;
    requestAnimationFrame(() => {
      container.scrollTop = targetScrollTop;
    });
  }
}
