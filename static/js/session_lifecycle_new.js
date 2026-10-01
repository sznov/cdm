import { createSession } from './sessions.js';

function setNewSessionError(elements, text = "") {
  if (!elements.newSessionError) return;
  const message = String(text || "").trim();
  elements.newSessionError.textContent = message;
  elements.newSessionError.hidden = !message;
}

export async function openNewSessionModal(context) {
  const { elements } = context;
  if (!elements.newSessionModal) return;
  const configurationError = context.runtimeConfigurationError();
  setNewSessionError(elements, configurationError);
  const config = context.getAppConfig();
  if (elements.runtimeHarnessSelect) {
    elements.runtimeHarnessSelect.value = configurationError ? "" : config.default_runtime_harness_id;
    elements.runtimeHarnessSelect.setAttribute("aria-invalid", configurationError ? "true" : "false");
    context.onRuntimeHarnessChanged();
  }
  if (elements.specification) {
    elements.specification.value = "";
    elements.specification.scrollTop = 0;
  }
  context.resetSpecificationFileUpload();
  const details = elements.newSessionModal.querySelector("details");
  if (details) details.open = false;
  elements.newSessionModal.scrollTop = 0;
  context.updateRuntimeRunControls();
  elements.newSessionModal.showModal();
  requestAnimationFrame(() => {
    elements.newSessionModal.scrollTop = 0;
    const form = elements.newSessionModal.querySelector(".modal-card");
    if (form) form.scrollTop = 0;
    if (elements.specification) elements.specification.scrollTop = 0;
  });
}

export async function createSessionAndStart(context) {
  const configurationError = context.runtimeConfigurationError();
  setNewSessionError(context.elements, configurationError);
  if (configurationError) {
    context.setStatus(configurationError, { updatePhasePanel: false });
    return;
  }
  const specification = context.elements.specification?.value.trim() || "";
  if (!specification) {
    context.setStatus("Paste or load a specification first.", { updatePhasePanel: false });
    setNewSessionError(context.elements, "Paste or load a specification first.");
    return;
  }
  const config = context.getAppConfig();
  const runtimeHarnessId = context.elements.runtimeHarnessSelect?.value || config.default_runtime_harness_id;
  const runtimeHarness = context.selectedRuntimeHarnessSummary?.();
  let modelBindings;
  try {
    modelBindings = context.modelBindingsFromControls(runtimeHarnessId);
  } catch (error) {
    const message = error?.message || "Invalid model settings.";
    context.setStatus(message, { updatePhasePanel: false });
    setNewSessionError(context.elements, message);
    return;
  }
  const payload = {
    runtime_harness_id: runtimeHarnessId,
    harness_runtime_config: context.workflowRuntimeConfigFromControls(runtimeHarnessId),
    model_bindings: modelBindings,
    specification,
  };
  if (runtimeHarness?.definition_revision) {
    payload.harness_definition_revision = runtimeHarness.definition_revision;
  }
  let data;
  try {
    data = await createSession(payload);
  } catch (error) {
    const message = error?.message || "Could not create session.";
    context.setStatus(message, { updatePhasePanel: false });
    setNewSessionError(context.elements, message);
    return;
  }
  context.setCurrentSession(data.session);
  context.setSelectedSessionId(data.session.session_id);
  if (context.elements.newSessionModal?.open) context.elements.newSessionModal.close();
  context.updateSessionWorkspace();
  await context.loadSessions();
  await context.run({ sessionId: context.selectedSessionId() });
}
