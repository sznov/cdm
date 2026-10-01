import {
  formatEmbeddedJsonForDisplay,
  formatJson,
  formatLabeledJsonSectionsForDisplay,
} from "./format_json.js";

export function formatPromptPayload(payload) {
  const messages = Array.isArray(payload.messages) ? payload.messages : [];
  const hasSystemMessage = messages.some((message) => String(message?.role || "").toLowerCase() === "system");
  const parts = [];
  if (typeof payload.system_prompt === "string" && !hasSystemMessage) {
    parts.push(`SYSTEM\n${payload.system_prompt || ""}`);
  }
  for (const message of messages) {
    parts.push(`${String(message.role || "message").toUpperCase()}\n${message.content || ""}`);
  }
  return parts.join("\n\n---\n\n");
}

export function modelInputTextFromPayload(payload) {
  if (!payload || typeof payload !== "object") return "";
  if (Array.isArray(payload.messages) || typeof payload.system_prompt === "string") {
    return formatPromptPayload(payload);
  }
  if (typeof payload.model_input === "string") return payload.model_input;
  if (typeof payload.prompt === "string") return payload.prompt;
  if (typeof payload.input_prompt === "string") return payload.input_prompt;
  if (payload.model_input && typeof payload.model_input === "object") return formatJson(payload.model_input);
  if (payload.request_body && typeof payload.request_body === "object") return formatJson(payload.request_body);
  return "";
}

export function replaceThoughtMarkersForDisplay(output) {
  const text = String(output || "").trim();
  if (!text) return "";
  return text
    .replace(/<\s*thought\s*>/gi, "Thinking...\n")
    .replace(/<\s*\/\s*thought\s*>/gi, "\nStopped thinking.\n\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function formatModelOutputForDisplay(output) {
  const normalized = replaceThoughtMarkersForDisplay(output);
  return formatEmbeddedJsonForDisplay(formatLabeledJsonSectionsForDisplay(normalized));
}
