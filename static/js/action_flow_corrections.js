import {
  streamCorrectionEvents,
  streamCorrectionSequenceEvents,
} from './streams.js';
import { ensureSelectedRunId } from './action_flow_run_selection.js';
import { runActionBlocked } from './state.js';

export async function sendFreeformCorrection(context, messageOverride = "") {
  const runId = ensureSelectedRunId(context);
  if (!runId) {
    context.setStatus("Select a run before sending a correction.");
    return;
  }
  const sessionId = context.selectedSessionId();
  if (runActionBlocked(runId)) {
    context.setStatus("Wait for the current operation on this run before sending another correction.");
    return;
  }
  const message = String(messageOverride || context.elements.correctionText?.value || "").trim();
  if (!message) {
    context.setStatus("Write a correction first.");
    context.updateCorrectionChatControls();
    return;
  }
  const operation = context.beginRunOperation(runId, "correction");
  if (!operation) {
    context.setStatus("Wait for the current operation on this run before sending another correction.");
    return;
  }
  if (context.elements.sendCorrectionButton) context.elements.sendCorrectionButton.disabled = true;
  context.appendCorrectionChatMessage("user", message, { dedupeAny: true });
  context.startCorrectionStreamChat();
  context.upsertCorrectionStreamChat("Generating correction patch operations...");
  context.setStatus("Generating correction patch operations...");
  try {
    await streamCorrectionEvents(runId, { message }, {
      routeEnvelope: context.handleRunEnvelope,
      sessionId,
    });
    await context.loadRuns();
    if (context.selectedRunId() === runId) {
      if (context.elements.correctionText) context.elements.correctionText.value = "";
      await context.refreshCurrentSessionRecord({ expectedRunId: runId, expectedSessionId: sessionId });
    }
  } catch (error) {
    if (context.selectedRunId() === runId) {
      context.clearCorrectionStreamChat();
      context.appendCorrectionChatMessage("assistant", `Correction failed: ${error.message}`, { dedupe: true });
    }
    throw error;
  } finally {
    context.finishRunOperation(runId, operation.id);
    if (context.selectedRunId() === runId) {
      context.updatePhasePanel("");
      context.updateCorrectionChatControls();
      context.updateQuestionChatControls();
    }
  }
}

export async function runCorrectionSequence(context) {
  const runId = ensureSelectedRunId(context);
  if (!runId) {
    context.setStatus("Select a run before running a correction sequence.");
    return;
  }
  const sessionId = context.selectedSessionId();
  if (runActionBlocked(runId)) {
    context.setStatus("Wait for the current operation on this run before running a correction sequence.");
    return;
  }
  const templateId = context.elements.correctionTemplateSelect?.value || context.defaultCorrectionTemplateId();
  const template = context.selectedCorrectionTemplate(templateId);
  if (!template) {
    context.setStatus("Select a correction template first.");
    context.updateCorrectionChatControls();
    return;
  }
  const operation = context.beginRunOperation(runId, "correction_sequence");
  if (!operation) {
    context.setStatus("Wait for the current operation on this run before running a correction sequence.");
    return;
  }
  if (context.elements.runCorrectionSequenceButton) context.elements.runCorrectionSequenceButton.disabled = true;
  const title = template.name || template.id;
  context.appendCorrectionChatMessage("assistant", `Running ${title}...`, { dedupe: true });
  context.setStatus(`Running ${title}...`);
  try {
    await streamCorrectionSequenceEvents(runId, { template_id: template.id }, {
      routeEnvelope: context.handleRunEnvelope,
      sessionId,
    });
    await context.loadRuns();
    if (context.selectedRunId() === runId) {
      await context.refreshCurrentSessionRecord({ expectedRunId: runId, expectedSessionId: sessionId });
    }
  } catch (error) {
    if (context.selectedRunId() === runId) {
      context.appendCorrectionChatMessage("assistant", `Correction sequence failed: ${error.message}`, { dedupe: true });
    }
    throw error;
  } finally {
    context.finishRunOperation(runId, operation.id);
    if (context.selectedRunId() === runId) {
      context.updatePhasePanel("");
      context.updateCorrectionChatControls();
      context.updateQuestionChatControls();
    }
  }
}
