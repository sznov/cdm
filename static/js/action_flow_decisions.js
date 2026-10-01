import { applyDecisionPatchChoices } from './runs.js';
import { ensureSelectedRunId } from './action_flow_run_selection.js';
import { runActionBlocked } from './state.js';
import { syncRunOperationTrace } from './streams.js';

export async function applySelectedDecisionPatches(context) {
  const runId = ensureSelectedRunId(context);
  if (!runId) {
    context.setStatus("Select a run before applying decision patches.");
    return;
  }
  const sessionId = context.selectedSessionId();
  if (runActionBlocked(runId)) {
    context.setStatus("Wait for the current operation on this run before applying decision patches.");
    return;
  }
  if (!context.decisionApplyPhasesComplete()) {
    context.setStatus("Decisions can be applied after all generation phases finish.");
    context.updateApplyDecisionButtonState();
    return;
  }
  const decisions = context.selectedDecisionChoices();
  if (!decisions.length) {
    context.setStatus("Choose at least one decision option.");
    return;
  }
  const operation = context.beginRunOperation(runId, "decision");
  if (!operation) {
    context.setStatus("Wait for the current operation on this run before applying decision patches.");
    return;
  }
  if (context.elements.applyDecisionPatchesButton) context.elements.applyDecisionPatchesButton.disabled = true;
  context.setStatus(`Applying ${decisions.length} decision(s)...`);
  let operationError = null;
  try {
    const payload = await applyDecisionPatchChoices(runId, decisions);
    await context.loadRuns();
    if (context.selectedRunId() !== runId) return;
    if (payload.chat_message?.content) {
      context.appendUnifiedChatMessage("user", payload.chat_message.content, {
        dedupeAny: true,
        collapsible: true,
        collapsed: true,
      });
    }
    context.updateDecisionPatches(payload.decision_patches || []);
    context.applyModelSnapshotPayload(runId, payload);
    context.setStatus(
      `Decision patches applied: ${payload.accepted_count || 0} accepted/already satisfied, ${payload.noted_count || 0} noted, ${payload.rejected_count || 0} rejected.`
    );
    await context.refreshCurrentSessionRecord({ expectedRunId: runId, expectedSessionId: sessionId });
  } catch (error) {
    operationError = error;
    if (context.selectedRunId() === runId) context.renderDecisionPatches();
    throw error;
  } finally {
    let traceSyncError = null;
    try {
      await syncRunOperationTrace(runId, { routeEnvelope: context.handleRunEnvelope });
    } catch (syncError) {
      traceSyncError = syncError;
      if (operationError) {
        console.warn(`Could not reconcile the trace for failed decision operation on ${runId}.`, syncError);
      }
    }
    context.finishRunOperation(runId, operation.id);
    if (context.selectedRunId() === runId) {
      context.updateApplyDecisionButtonState();
      context.updateUnifiedChatControls();
    }
    if (traceSyncError && !operationError) throw traceSyncError;
  }
}
