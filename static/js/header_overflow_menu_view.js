import { els } from "./dom.js";

export function isHeaderActionDisabled(element) {
  if (!element) return true;
  if (element instanceof HTMLAnchorElement) {
    return element.classList.contains("disabled") || element.getAttribute("aria-disabled") === "true" || !element.href || element.href.endsWith("#");
  }
  return Boolean(element.disabled);
}

function labelForHeaderOverflowAction(candidate) {
  const element = candidate?.element;
  if (!element) return candidate?.label || "Action";
  return element.getAttribute("aria-label") || element.title || candidate.label || element.textContent?.trim() || "Action";
}

export function renderHeaderOverflowMenu(hiddenCandidates, onActivate) {
  if (!els.headerOverflowMenu) return;
  els.headerOverflowMenu.innerHTML = "";
  for (const candidate of hiddenCandidates) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "overflow-menu-item";
    item.setAttribute("role", "menuitem");
    item.textContent = labelForHeaderOverflowAction(candidate);
    item.disabled = isHeaderActionDisabled(candidate.element);
    item.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      onActivate?.(candidate.element);
    });
    els.headerOverflowMenu.append(item);
  }
}

export function closeHeaderOverflowMenu() {
  if (els.headerOverflowMenu) els.headerOverflowMenu.hidden = true;
  if (els.headerOverflowButton) els.headerOverflowButton.setAttribute("aria-expanded", "false");
}

export function toggleHeaderOverflowMenu() {
  if (!els.headerOverflowMenu || !els.headerOverflowButton || els.headerOverflow.hidden) return;
  const nextOpen = els.headerOverflowMenu.hidden;
  els.headerOverflowMenu.hidden = !nextOpen;
  els.headerOverflowButton.setAttribute("aria-expanded", nextOpen ? "true" : "false");
}
