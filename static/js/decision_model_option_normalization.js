import { cleanDecisionPatchText } from "./decision_patch_text.js";
import { decisionOperationValidationIssue } from "./decision_model_validation.js";
import { decisionPatchApplyLabel } from "./decision_model_option_labels.js";

function isCustomTextOption(option = {}, label = "") {
  const normalizedLabel = label.toLowerCase();
  return (
    option.id === "custom" ||
    normalizedLabel.includes("something else") ||
    Boolean(option.requires_text || option.requiresText)
  );
}

function isKeepOption(optionId = "", label = "") {
  const normalizedLabel = label.toLowerCase();
  return (
    optionId === "keep" ||
    normalizedLabel === "keep as-is" ||
    normalizedLabel === "keep as is" ||
    normalizedLabel.startsWith("keep ")
  );
}

function generatedOperationOptionId(hasOptionOperation, operationOptionCount, operationIndex, index) {
  if (!hasOptionOperation) return `option-${index + 1}`;
  return operationOptionCount === 1 ? "apply" : `apply-${operationIndex}`;
}

function shouldReplaceOperationLabel(optionOperation, label = "") {
  return optionOperation?.op === "setIdentifier" || !label || /^apply(?: patch| option \d+)?$/i.test(label);
}

export function decisionOptionsForPatch(patch = {}, model = null) {
  const existing = Array.isArray(patch.options) ? patch.options.filter((option) => option && typeof option === "object") : [];
  const options = [];
  let hasOperationOption = false;
  let hasKeepOption = false;
  const patchOperationText = patch.operation ? JSON.stringify(patch.operation) : "";
  const operationOptionCount = existing.filter((option) => option.operation || option.patch).length;
  let operationIndex = 0;
  for (let index = 0; index < existing.length; index += 1) {
    const option = existing[index];
    const optionOperation = option.operation || option.patch || null;
    const hasOptionOperation = Boolean(optionOperation);
    if (hasOptionOperation) operationIndex += 1;
    let optionId = String(option.id || option.option_id || "").trim();
    if (!optionId) {
      optionId = generatedOperationOptionId(hasOptionOperation, operationOptionCount, operationIndex, index);
    }
    let label = cleanDecisionPatchText(option.label || option.title || optionId);
    if (isCustomTextOption(option, label)) continue;
    if (hasOptionOperation) {
      hasOperationOption = true;
      const explicitId = String(option.id || option.option_id || "").trim();
      if (!explicitId && patchOperationText && JSON.stringify(optionOperation) === patchOperationText && operationOptionCount === 1) {
        optionId = "apply";
      }
      if (shouldReplaceOperationLabel(optionOperation, label)) {
        label = decisionPatchApplyLabel(patch, optionOperation, model);
      }
    }
    if (isKeepOption(optionId, label)) {
      optionId = "keep";
      label = "Keep as-is";
      hasKeepOption = true;
    }
    const disabledReason = hasOptionOperation ? decisionOperationValidationIssue(optionOperation, model) : "";
    options.push({
      ...option,
      id: optionId,
      label,
      operation: hasOptionOperation ? optionOperation : null,
      requiresText: false,
      disabled: Boolean(disabledReason),
      disabledReason,
    });
  }
  if (patch.operation && !hasOperationOption) {
    const disabledReason = decisionOperationValidationIssue(patch.operation, model);
    options.unshift({
      id: "apply",
      label: decisionPatchApplyLabel(patch, null, model),
      operation: patch.operation,
      requiresText: false,
      disabled: Boolean(disabledReason),
      disabledReason,
    });
  }
  if (!hasKeepOption) options.push({ id: "keep", label: "Keep as-is", operation: null, requiresText: false });
  return options;
}
