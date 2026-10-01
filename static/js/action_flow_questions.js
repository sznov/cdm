import { streamQuestionEvents } from './streams.js';
import { ensureSelectedRunId } from './action_flow_run_selection.js';
import { runActionBlocked } from './state.js';

export async function sendQuestion(context) {
  const runId = ensureSelectedRunId(context);
  if (!runId) {
    context.setStatus("Select a run before asking a question.");
    return;
  }
  const sessionId = context.selectedSessionId();
  if (runActionBlocked(runId)) {
    context.setStatus("Wait for the current operation on this run before asking a question.");
    return;
  }
  const question = context.elements.questionText?.value.trim() || "";
  if (!question) {
    context.setStatus("Write a question first.");
    context.updateQuestionChatControls();
    return;
  }
  const operation = context.beginRunOperation(runId, "question");
  if (!operation) {
    context.setStatus("Wait for the current operation on this run before asking another question.");
    return;
  }
  if (context.elements.sendQuestionButton) context.elements.sendQuestionButton.disabled = true;
  context.appendQuestionChatMessage("user", question, { dedupeAny: true });
  context.appendQuestionChatMessage("assistant", "Thinking...", { dedupe: true });
  context.setStatus("Asking the model...");
  try {
    await streamQuestionEvents(runId, { question }, {
      routeEnvelope: context.handleRunEnvelope,
      sessionId,
    });
    await context.loadRuns();
    if (context.selectedRunId() === runId) {
      if (context.elements.questionText) context.elements.questionText.value = "";
      await context.refreshCurrentSessionRecord({ expectedRunId: runId, expectedSessionId: sessionId });
    }
  } catch (error) {
    if (context.selectedRunId() === runId) {
      context.appendQuestionChatMessage("assistant", `Question failed: ${error.message}`, { dedupe: true });
    }
    throw error;
  } finally {
    context.finishRunOperation(runId, operation.id);
    if (context.selectedRunId() === runId) {
      context.updatePhasePanel("");
      context.updateQuestionChatControls();
      context.updateCorrectionChatControls();
    }
  }
}
