import { appendChatMessage } from './chat_messages.js';

export function appendBuildLogModalMessage(container, role, text, options = {}) {
  return appendChatMessage(container, role, text, {
    ...options,
    label: options.label || (role === "user" ? "Prompt" : "Response"),
    follow: options.follow ?? false,
  });
}

export function buildLogModalMessageRow(elements = {}, messageId = "") {
  if (!messageId || !elements.buildLogModalBody) return null;
  const target = `modal-${messageId}`;
  return [...elements.buildLogModalBody.querySelectorAll(".build-log-row")].find(
    (row) => row.dataset.messageId === target
  ) || null;
}
