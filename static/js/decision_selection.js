import {
  decisionPatchConflictKey,
} from "./decision_patch_conflicts.js";
import {
  decisionPatchRequiresChoice,
} from "./decision_patch_status.js";

export function decisionOptionInputs(roots = []) {
  return roots.flatMap((root) => [...root.querySelectorAll('input[type="radio"][data-decision-option]')]);
}

export function clearConflictingDecisionSelections(selectedInput, roots = []) {
  if (!selectedInput?.checked) return;
  const key = selectedInput.dataset.decisionConflictKey || "";
  if (!key) return;
  const patchId = selectedInput.dataset.patchId || "";
  for (const input of decisionOptionInputs(roots)) {
    if (input === selectedInput) continue;
    if ((input.dataset.decisionConflictKey || "") !== key) continue;
    if ((input.dataset.patchId || "") === patchId) continue;
    input.checked = false;
  }
}

export function selectedDecisionConflictKeySet(roots = []) {
  const keys = decisionOptionInputs(roots)
    .filter((input) => input.checked && !input.disabled)
    .map((input) => input.dataset.decisionConflictKey || "")
    .filter(Boolean);
  return new Set(keys);
}

export function selectedDecisionChoices(roots = []) {
  const choices = roots
    .flatMap((root) => [...root.querySelectorAll('input[type="radio"][data-decision-option]:checked:not(:disabled)')])
    .map((input) => {
      const row = input.closest(".decision-patch");
      const textarea = [...(row?.querySelectorAll("textarea[data-option-text]") || [])].find(
        (candidate) => candidate.dataset.optionText === (input.dataset.optionId || "")
      );
      return {
        patch_id: input.dataset.patchId || "",
        option_id: input.dataset.optionId || input.value || "apply",
        label: input.dataset.optionLabel || "",
        custom_text: textarea?.value.trim() || "",
      };
    })
    .filter((choice) => choice.patch_id);
  const seen = new Set();
  return choices.filter((choice) => {
    if (seen.has(choice.patch_id)) return false;
    seen.add(choice.patch_id);
    return true;
  });
}

export function selectedDecisionPatchIdSet(choices = []) {
  return new Set(choices.map((choice) => choice.patch_id).filter(Boolean));
}

export function decisionPatchHasRecordedChoice(patch = {}) {
  return Boolean(patch.selected_option_id || patch.selected_option_label || patch.applied_result);
}

export function decisionPatchIsSupersededBySelectedConflict(patch = {}, context = {}) {
  if (!decisionPatchRequiresChoice(patch)) return false;
  if (decisionPatchHasRecordedChoice(patch)) return false;
  const selectedPatchIds = context.selectedPatchIds || new Set();
  const selectedConflictKeys = context.selectedConflictKeys || new Set();
  const patchId = String(patch.id || "");
  if (patchId && selectedPatchIds.has(patchId)) return false;
  const conflictKey = decisionPatchConflictKey(patch);
  return Boolean(conflictKey && selectedConflictKeys.has(conflictKey));
}

export function decisionPatchIsUnresolved(patch = {}, context = {}) {
  if (!decisionPatchRequiresChoice(patch)) return false;
  if (decisionPatchHasRecordedChoice(patch)) return false;
  const selectedPatchIds = context.selectedPatchIds || new Set();
  const selectedConflictKeys = context.selectedConflictKeys || new Set();
  const patchId = String(patch.id || "");
  if (patchId && selectedPatchIds.has(patchId)) return false;
  const conflictKey = decisionPatchConflictKey(patch);
  if (conflictKey && selectedConflictKeys.has(conflictKey)) return false;
  return true;
}

export function pendingDecisionPatchCount(patches = [], context = {}) {
  return patches.filter((patch) => decisionPatchIsUnresolved(patch, context)).length;
}
