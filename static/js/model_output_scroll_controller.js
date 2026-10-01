import { isScrolledNearBottom } from "./chat_messages.js";

export function updateModelOutputJump(context) {
  const { rawOutput, modelOutputJump } = context.elements;
  if (!rawOutput || !modelOutputJump) return;
  const hasOutput = Boolean(rawOutput.textContent.trim());
  modelOutputJump.hidden = !(hasOutput && !isScrolledNearBottom(rawOutput, 72));
  modelOutputJump.classList.toggle("is-visible", !modelOutputJump.hidden);
}

export function jumpModelOutputToCurrent(context) {
  const output = context.elements.rawOutput;
  if (!output) return;
  output.scrollTop = output.scrollHeight;
  updateModelOutputJump(context);
}
