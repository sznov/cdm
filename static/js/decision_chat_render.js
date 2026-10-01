import {
  renderDecisionRailView,
  updateDecisionOptionControlsView,
  updateDecisionPendingIndicatorView,
} from './decision_ui.js';
import {
  decisionApplyPhasesComplete,
  decisionPatchIsSupersededBySelectedConflict,
  pendingDecisionPatchCount,
} from './decision_chat_state.js';
import {
  updateUnifiedChatControls,
} from './decision_chat_input_controls.js';
import {
  getAppConfig,
  runtimeHarnessSummaryById,
} from './runtime.js';

function bindingFromRecord(record = {}) {
  const bindings = record?.model_bindings;
  if (!bindings || typeof bindings !== "object") return {};
  return bindings.default && typeof bindings.default === "object" ? bindings.default : bindings;
}

function displayProviderName(providerId = "", fallback = "") {
  const provider = String(providerId || "").trim();
  if (!provider) return fallback || "";
  return getAppConfig().providers?.[provider]?.label || fallback || provider;
}

function buildRunInfo(context) {
  const run = context.selectedRunRecord?.() || {};
  const session = context.currentSession?.() || {};
  const runBinding = bindingFromRecord(run);
  const sessionBinding = bindingFromRecord(session);
  const harnessId = run.runtime_harness_id || session.runtime_harness_id || "";
  const harnessSummary = harnessId ? runtimeHarnessSummaryById(harnessId) : null;
  const providerId = runBinding.provider || sessionBinding.provider || run.provider || session.provider || "";
  return {
    harness: run.runtime_harness_name || session.runtime_harness_name || harnessSummary?.name || harnessId,
    provider: run.provider_label || session.provider_label || displayProviderName(providerId),
    model: runBinding.model || sessionBinding.model || run.model || session.model,
  };
}

export function renderDecisionPatches(context) {
  const { elements } = context;
  if (elements.decisionPatchList) {
    elements.decisionPatchList.innerHTML = "";
    if (!(context.currentDecisionPatches() || []).length) {
      elements.decisionPatchList.textContent = "No decision points or assumptions available.";
    }
  }
  if (!context.renderingSessionTranscript()) context.renderSessionChat();
  updateDecisionOptionControls(context);
  updateDecisionPendingIndicator(context);
  updateApplyDecisionButtonState(context);
}

export function updateDecisionOptionControls(context, event = null) {
  updateDecisionOptionControlsView({
    elements: context.elements,
    event,
    isSuperseded: (patch, selectedPatchIds, selectedConflictKeys) =>
      decisionPatchIsSupersededBySelectedConflict(context, patch, selectedPatchIds, selectedConflictKeys),
    patches: context.currentDecisionPatches() || [],
  });
  updateApplyDecisionButtonState(context);
  updateUnifiedChatControls(context);
}

export function updateDecisionPendingIndicator(context) {
  updateDecisionPendingIndicatorView(context.elements, pendingDecisionPatchCount(context));
}

export function updateApplyDecisionButtonState(context) {
  const button = context.elements.applyDecisionPatchesButton;
  if (!button) return;
  button.hidden = true;
  button.disabled = true;
  button.title = "Use Send to submit selected decisions.";
}

export function updateDecisionPatches(context, patches = []) {
  context.setCurrentDecisionPatches(Array.isArray(patches) ? patches : []);
  renderDecisionPatches(context);
}

export function renderDecisionRail(context) {
  renderDecisionRailView({
    elements: context.elements,
    isSuperseded: (patch, selectedPatchIds, selectedConflictKeys) =>
      decisionPatchIsSupersededBySelectedConflict(context, patch, selectedPatchIds, selectedConflictKeys),
    model: context.currentWorkingModel(),
    onOptionChange: (event) => updateDecisionOptionControls(context, event),
    patches: context.currentDecisionPatches() || [],
    phasesComplete: decisionApplyPhasesComplete(context),
    runInfo: buildRunInfo(context),
    specification: context.currentSession()?.specification || "",
  });
  context.updateCompactReviewRailState();
}
