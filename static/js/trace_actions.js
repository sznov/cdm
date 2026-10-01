import { traceIconSvg } from './icons.js';

function setIconButton(button, icon, title, classes = []) {
  if (!button) return;
  if (classes.length) button.classList.add(...classes);
  button.innerHTML = traceIconSvg(icon);
  button.setAttribute("aria-label", title);
  button.title = title;
}

export function applyModelToolbarIconsView(elements = {}, options = {}) {
  setIconButton(elements.diagramFitButton, "fit", "Fit to view", ["toolbar-icon-action"]);
  setIconButton(elements.diagramResetButton, "reset", "Reset zoom", ["toolbar-icon-action"]);
  setIconButton(elements.viewPlantumlSourceButton, "puml", "View PlantUML source", [
    "toolbar-icon-action",
    "trace-icon-puml",
  ]);
  setIconButton(elements.viewJsonIrButton, "json", "View JSON IR", [
    "toolbar-icon-action",
    "trace-icon-json",
  ]);
  setIconButton(elements.workingModelDiagramLink, "diagram", "Open diagram in a new tab", [
    "toolbar-icon-action",
    "trace-icon-diagram",
  ]);
  setIconButton(elements.renameSessionButton, "corrections", "Rename title", ["header-icon-button"]);
  setIconButton(elements.refreshRuns, "refresh", "Refresh", ["toolbar-icon-action"]);
  setIconButton(elements.jumpToCurrent, "up", "Jump to current", ["toolbar-icon-action"]);
  setIconButton(elements.sendUnifiedChatButton, "send", "Send", [
    "toolbar-icon-action",
    "send-icon-button",
  ]);
  setIconButton(elements.viewBuildLogButton, "log", "View build log", [
    "toolbar-icon-action",
    "trace-icon-log",
  ]);
  setIconButton(elements.headerOverflowButton, "more", "More actions", []);
  setIconButton(elements.copyTextModalButton, "copy", "Copy", []);
  setIconButton(elements.downloadTextModalButton, "download", "Download", []);
  document.querySelectorAll(".corrections-toggle .tool-symbol").forEach((node) => {
    node.innerHTML = traceIconSvg("corrections");
  });
  options.updateDiagramControlState?.();
  options.scheduleHeaderOverflowUpdate?.();
}

export function appendTraceActionsView(container, entry, actions = [], options = {}) {
  if (!container) return null;
  const actionsNode = document.createElement("div");
  actionsNode.className = "trace-inline-actions";
  for (const action of actions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "trace-icon-action";
    const icon = traceIconSvg(action.label);
    if (icon) {
      button.classList.add(`trace-icon-${action.label}`);
      button.innerHTML = icon;
    } else {
      button.textContent = action.label;
    }
    button.title = action.title;
    button.setAttribute("aria-label", action.title);
    button.disabled = Boolean(action.disabled);
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const selectionEntry = action.selectEntry || entry;
      options.onSelect?.(selectionEntry);
      action.handler?.();
    });
    actionsNode.append(button);
  }
  container.append(actionsNode);
  return actionsNode;
}
