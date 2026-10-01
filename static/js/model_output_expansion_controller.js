import { updateModelOutputJump } from "./model_output_scroll_controller.js";

export function setModelOutputExpanded(context, expanded) {
  context.setModelOutputExpanded(Boolean(expanded));
  context.elements.activeSessionWorkspace?.classList.toggle("output-expanded", context.modelOutputExpanded());
  const button = context.elements.modelOutputToggle;
  if (button) {
    button.textContent = context.modelOutputExpanded() ? "Collapse output" : "Expand output";
    button.title = context.modelOutputExpanded()
      ? "Return model output to compact height"
      : "Give model output more height";
  }
  updateModelOutputJump(context);
}

export function toggleModelOutputExpanded(context) {
  setModelOutputExpanded(context, !context.modelOutputExpanded());
}
