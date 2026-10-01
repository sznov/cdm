import {
  formatEmbeddedJsonForDisplay,
  formatLabeledJsonSectionsForDisplay,
  formatPromptPayload,
} from "./format.js";

export function tracePromptText(entry) {
  return String(entry?.prompt || formatPromptPayload(entry?.payload || "") || "");
}

export function traceOutputText(entry) {
  return String(
    entry?.output ||
      entry?.rawOutput ||
      entry?.payload?.raw_output ||
      entry?.payload?.answer ||
      entry?.payload?.error ||
      ""
  );
}

export function traceChatMarkdown(text = "") {
  const raw = String(text || "").trim();
  if (!raw) return "";
  const labeled = formatLabeledJsonSectionsForDisplay(raw);
  let formatted = (labeled === raw ? formatEmbeddedJsonForDisplay(raw) : labeled)
    .replace(/^\s*SYSTEM\s*$/gm, "### System")
    .replace(/^\s*USER\s*$/gm, "### User")
    .replace(/^\s*ASSISTANT\s*$/gm, "### Assistant")
    .replace(/^\s*---\s*$/gm, "");
  if (!formatted.includes("```") && /^[\s\n]*[\[{]/.test(formatted)) {
    formatted = `\`\`\`json\n${formatted}\n\`\`\``;
  }
  return formatted;
}
