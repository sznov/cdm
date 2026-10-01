import {
  getRun,
} from './runs.js';
import { runOperationPending, runStateById } from './state.js';
import {
  CORRECTION_LOG_EMPTY_TEXT,
  QUESTION_LOG_EMPTY_TEXT,
  resetSideChatLog,
} from './side_chat_logs.js';

export function clearRunOutputs(context, options = {}) {
  const runId = context.selectedRunId();
  if (!runOperationPending(runId) && !options.keepTerminalStatus) {
    context.setLastRunTerminalStatus(null);
  }
  context.setScrollableText(context.elements.rawOutput, "", { follow: true });
  if (context.elements.history) context.elements.history.innerHTML = "";
  if (context.elements.workingModel) context.elements.workingModel.textContent = "";
  if (context.elements.plantuml) context.elements.plantuml.textContent = "";
  if (context.elements.inputPrompt) context.elements.inputPrompt.textContent = "";
  if (runId && options.clearRunState !== false) {
    context.setCurrentGenerationOutput(runId, "");
    context.setCurrentWorkingModel(runId, null);
    context.setCurrentStructuredModel(runId, null);
    context.setCurrentPlantuml(runId, "");
    context.setCurrentPlantumlUrl(runId, "");
  }
  context.setCurrentDecisionPatches([]);
  if (context.elements.correctionText) context.elements.correctionText.value = "";
  resetSideChatLog(context.elements.correctionChatLog, CORRECTION_LOG_EMPTY_TEXT);
  if (context.elements.questionText) context.elements.questionText.value = "";
  resetSideChatLog(context.elements.questionChatLog, QUESTION_LOG_EMPTY_TEXT);
  context.updateArtifactLinks();
  context.clearInlineDiagram();
  context.renderDecisionPatches();
  context.updateCorrectionChatControls();
  context.updateQuestionChatControls();
  context.updateUnifiedChatControls();
  context.updateModelOutputJump();
  context.updateChatPanelVisibility();
}

export function applyFinalRunResult(context, jobId, run = {}) {
  const finalResult = run.result || {};
  if (!(finalResult.working_model || finalResult.structured_model || finalResult.plantuml)) return false;
  const artifacts = runStateById(jobId)?.artifacts;
  return context.applyModelSnapshotPayload(jobId, {
    model_snapshot: finalResult.working_model || artifacts?.workingModel || null,
    structured_model: finalResult.structured_model || artifacts?.structuredModel || null,
    plantuml: finalResult.plantuml || artifacts?.plantuml || "",
  });
}

export function applyRunSummaryStatus(context, summary = {}, jobId = context.selectedRunId()) {
  const status = summary.status || runStateById(jobId)?.status || "";
  if (status && jobId) context.setSelectedRunStatus(jobId, status);
  if (context.runStatusIsActive(status)) {
    context.setLastRunTerminalStatus(null);
    context.setRunning(true);
    return true;
  }
  const terminalStatus = context.terminalStatusFromRunStatus(status);
  if (terminalStatus) context.setLastRunTerminalStatus(terminalStatus);
  context.setRunning(false);
  return false;
}

export async function refreshSelectedRunSummary(context, jobId = context.selectedRunId()) {
  if (!jobId || context.selectedRunId() !== jobId) return;
  const payload = await getRun(jobId, { includeTrace: false, cache: "no-store" });
  if (context.selectedRunId() !== jobId) return;
  const run = payload.run || {};
  context.setSelectedRunStatus(jobId, run.status || payload.summary?.status || runStateById(jobId)?.status || "");
  applyRunSummaryStatus(context, payload.summary || run, jobId);
  applyFinalRunResult(context, jobId, run);
  context.updateDecisionPatches(payload.decision_patches || run.decision_patches || []);
  context.updateRetryRunControls();
  context.updateCorrectionChatControls();
  context.updateQuestionChatControls();
  context.updateUnifiedChatControls();
  context.refreshModelOutputMarkdown();
  context.updateSessionWorkspace();
}
