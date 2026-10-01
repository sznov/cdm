import { els } from "./dom.js";

const CHAT_PLACEHOLDER_COMPACT_WIDTH = 230;

export function autoGrowUnifiedChatTextarea() {
  const textarea = els.unifiedChatText;
  if (!textarea) return;
  const minHeight = 34;
  const maxHeight = 98;
  textarea.style.height = "auto";
  const nextHeight = Math.min(maxHeight, Math.max(minHeight, textarea.scrollHeight));
  const isScrollable = textarea.scrollHeight > maxHeight;
  textarea.style.height = `${nextHeight}px`;
  textarea.style.overflowY = isScrollable ? "auto" : "hidden";
  const shell = textarea.closest(".chat-textarea-shell");
  shell?.classList.toggle("is-expanded", nextHeight > minHeight + 8);
  shell?.classList.toggle("is-scrollable", isScrollable);
}

export function useCompactUnifiedChatPlaceholder() {
  const width =
    els.unifiedChatText?.getBoundingClientRect().width ||
    els.unifiedChatPanel?.getBoundingClientRect().width ||
    0;
  return width > 0 && width < CHAT_PLACEHOLDER_COMPACT_WIDTH;
}
