import {
  decisionPatchIsSupersededBySelectedConflict as decisionPatchIsSupersededBySelectedConflictValue,
  pendingDecisionPatchCount as pendingDecisionPatchCountForElements,
  selectedDecisionChoices as selectedDecisionChoicesForElements,
  selectedDecisionConflictKeySet as selectedDecisionConflictKeySetForElements,
  selectedDecisionPatchIdSet as selectedDecisionPatchIdSetForElements,
} from './decision_ui.js';
import { runActionBlocked } from './state.js';

export function selectedDecisionConflictKeySet(context) {
  return selectedDecisionConflictKeySetForElements(context.elements);
}

export function selectedDecisionPatchIdSet(context) {
  return selectedDecisionPatchIdSetForElements(context.elements);
}

export function decisionPatchIsSupersededBySelectedConflict(
  context,
  patch = {},
  selectedPatchIds = selectedDecisionPatchIdSet(context),
  selectedConflictKeys = selectedDecisionConflictKeySet(context)
) {
  return decisionPatchIsSupersededBySelectedConflictValue(patch, {
    elements: context.elements,
    selectedConflictKeys,
    selectedPatchIds,
  });
}

export function selectedDecisionChoices(context) {
  return selectedDecisionChoicesForElements(context.elements);
}

export function pendingDecisionPatchCount(context) {
  return pendingDecisionPatchCountForElements(context.currentDecisionPatches() || [], context.elements);
}

export function decisionApplyPhasesComplete(context) {
  const selected = context.selectedRunRecord();
  const selectedRunId = context.selectedRunId?.() || "";
  const operationBlocksSelected = runActionBlocked(selectedRunId);
  const statuses = [
    context.selectedRunStatus?.(),
    selected?.status,
    context.currentSession?.()?.status,
  ].map((status) => String(status || "").toLowerCase());
  const terminalComplete = statuses.includes("completed") || Boolean(context.guardedPosthocResultEntry());
  return (
    !operationBlocksSelected &&
    !context.selectedRunIsActive() &&
    terminalComplete
  );
}
