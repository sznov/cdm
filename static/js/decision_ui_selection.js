import {
  clearConflictingDecisionSelections as clearConflictingDecisionSelectionsForRoots,
  decisionOptionInputs as decisionOptionInputsForRoots,
  decisionPatchHasRecordedChoice as decisionPatchHasRecordedChoiceValue,
  decisionPatchIsSupersededBySelectedConflict as decisionPatchIsSupersededBySelectedConflictValue,
  decisionPatchIsUnresolved as decisionPatchIsUnresolvedValue,
  pendingDecisionPatchCount as pendingDecisionPatchCountValue,
  selectedDecisionChoices as selectedDecisionChoicesForRoots,
  selectedDecisionConflictKeySet as selectedDecisionConflictKeySetForRoots,
  selectedDecisionPatchIdSet as selectedDecisionPatchIdSetForChoices,
} from './decision_selection.js';

export function decisionRoots(elements = {}) {
  return [elements.decisionPatchList, elements.decisionRail].filter(Boolean);
}

export function decisionOptionInputs(elements = {}) {
  return decisionOptionInputsForRoots(decisionRoots(elements));
}

export function clearConflictingDecisionSelections(selectedInput, elements = {}) {
  clearConflictingDecisionSelectionsForRoots(selectedInput, decisionRoots(elements));
}

export function selectedDecisionConflictKeySet(elements = {}) {
  return selectedDecisionConflictKeySetForRoots(decisionRoots(elements));
}

export function selectedDecisionChoices(elements = {}) {
  return selectedDecisionChoicesForRoots(decisionRoots(elements));
}

export function selectedDecisionPatchIdSet(elements = {}) {
  return selectedDecisionPatchIdSetForChoices(selectedDecisionChoices(elements));
}

export function decisionPatchHasRecordedChoice(patch = {}) {
  return decisionPatchHasRecordedChoiceValue(patch);
}

export function decisionPatchIsSupersededBySelectedConflict(patch = {}, options = {}) {
  const elements = options.elements || {};
  const selectedPatchIds = options.selectedPatchIds || selectedDecisionPatchIdSet(elements);
  const selectedConflictKeys = options.selectedConflictKeys || selectedDecisionConflictKeySet(elements);
  return decisionPatchIsSupersededBySelectedConflictValue(patch, {
    selectedConflictKeys,
    selectedPatchIds,
  });
}

export function decisionPatchIsUnresolved(patch = {}, options = {}) {
  const elements = options.elements || {};
  const selectedPatchIds = options.selectedPatchIds || selectedDecisionPatchIdSet(elements);
  const selectedConflictKeys = options.selectedConflictKeys || selectedDecisionConflictKeySet(elements);
  return decisionPatchIsUnresolvedValue(patch, {
    selectedConflictKeys,
    selectedPatchIds,
  });
}

export function pendingDecisionPatchCount(patches = [], elements = {}) {
  const selectedPatchIds = selectedDecisionPatchIdSet(elements);
  const selectedConflictKeys = selectedDecisionConflictKeySet(elements);
  return pendingDecisionPatchCountValue(patches || [], {
    selectedConflictKeys,
    selectedPatchIds,
  });
}
