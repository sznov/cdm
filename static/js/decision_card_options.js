import {
  cleanDecisionPatchText,
} from "./decision_patch_text.js";
import { decisionOptionDomId } from "./decision_patch_dom.js";
import { decisionPatchConflictKey } from "./decision_patch_conflicts.js";
import { decisionOptionsForPatch } from "./decision_model_helpers.js";
import { renderDecisionSupersededNote } from "./decision_card_superseded.js";

function appendDecisionOptionWarning(optionRow, text) {
  if (!text) return;
  const warning = document.createElement("span");
  warning.className = "decision-option-warning";
  warning.textContent = text;
  optionRow.append(warning);
}

function appendDecisionOptionRows(body, row, patch, titleText, decisionOptions, options = {}) {
  const optionsContainer = document.createElement("div");
  optionsContainer.className = "decision-options";
  for (const option of decisionOptions) {
    const optionRow = document.createElement("label");
    optionRow.className = "decision-option";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = `decision-${patch.id || decisionOptionDomId(titleText)}`;
    input.value = option.id || "";
    input.dataset.patchId = patch.id || "";
    input.dataset.optionId = option.id || "";
    input.dataset.optionLabel = option.label || "";
    input.dataset.decisionOption = "true";
    const conflictKey = decisionPatchConflictKey(patch, option);
    if (conflictKey) input.dataset.decisionConflictKey = conflictKey;
    if (option.disabled) {
      input.disabled = true;
      optionRow.classList.add("is-disabled");
      optionRow.title = option.disabledReason || "This option cannot be applied to the current model.";
    }
    optionRow.append(input);
    if (!option.disabled && (option.reason || option.rationale)) optionRow.title = option.reason || option.rationale || "";

    const label = document.createElement("span");
    label.textContent = cleanDecisionPatchText(option.label || option.title || option.id || "Option");
    optionRow.append(label);

    appendDecisionOptionWarning(optionRow, option.disabledReason);
    if (options.onOptionChange) input.addEventListener("change", options.onOptionChange);
    optionsContainer.append(optionRow);
  }
  body.append(optionsContainer);
  renderDecisionSupersededNote(row, Boolean(options.isSuperseded?.(patch)));
}

function appendSelectedDecisionChoice(body, patch) {
  const selected = document.createElement("div");
  selected.className = "decision-selected-choice";
  selected.textContent = cleanDecisionPatchText(patch.selected_option_label || patch.selected_option_id || "");
  body.append(selected);
  const blockedReason = patch.applied_result?.reason || patch.validation_reason || "";
  if (blockedReason && String(patch.status || "").toLowerCase() === "rejected") {
    const warning = document.createElement("div");
    warning.className = "decision-option-warning decision-selected-warning";
    warning.textContent = cleanDecisionPatchText(blockedReason);
    body.append(warning);
  }
}

export function appendDecisionPatchChoiceControls(row, body, patch, titleText, options = {}) {
  const decisionOptions = options.actionable && !options.readOnly
    ? decisionOptionsForPatch(patch, options.model || null)
    : [];
  if (decisionOptions.length) {
    appendDecisionOptionRows(body, row, patch, titleText, decisionOptions, options);
  } else if (patch.selected_option_label || patch.selected_option_id) {
    appendSelectedDecisionChoice(body, patch);
  }
}
