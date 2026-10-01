export const CORRECTION_LOG_EMPTY_TEXT = "No corrections sent yet.";
export const QUESTION_LOG_EMPTY_TEXT = "No questions asked yet.";

export function resetSideChatLog(container, emptyText) {
  if (!container) return;
  container.textContent = emptyText;
}

export function appendSideChatMessage(container, kind, text, options = {}) {
  if (!container) return null;
  const value = text || "";
  const emptyText = options.emptyText || "";
  if (emptyText && container.textContent === emptyText) container.innerHTML = "";

  if (options.dedupeAny) {
    const existing = [...container.children].some(
      (candidate) => candidate?.dataset?.kind === kind && candidate?.dataset?.text === value
    );
    if (existing) return null;
  }

  if (options.dedupe) {
    const last = container.lastElementChild;
    if (last?.dataset?.kind === kind && last?.dataset?.text === value) return last;
  }

  const row = document.createElement("div");
  row.className = `correction-message ${kind}`;
  row.dataset.kind = kind;
  row.dataset.text = value;

  const label = document.createElement("strong");
  label.textContent = kind === "user" ? (options.userLabel || "You") : (options.assistantLabel || "LLM");

  const body = document.createElement("span");
  body.textContent = value;

  row.append(label, body);
  container.append(row);
  container.scrollTop = container.scrollHeight;
  return row;
}
