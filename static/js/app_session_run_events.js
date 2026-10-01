import { loadSpecificationFromFile, onModelBindingChanged, onModelSelectChanged, onProviderChanged, onRuntimeHarnessChanged, refreshSelectedProviderModels, stopProviderModelCatalogPolling, updateProviderModelRefreshUi, updateRuntimeRunControls } from './runtime.js';
import { on } from './app_event_utils.js';

export function bindSessionRunEvents(context) {
  const { elements } = context;

  on(elements.newSessionButton, "click", () => context.openNewSessionModal()
    .then(() => updateProviderModelRefreshUi())
    .catch(context.statusError));
  on(elements.closeSessionModalButton, "click", () => {
    elements.newSessionModal?.close();
    stopProviderModelCatalogPolling();
  });
  on(elements.newSessionModal, "close", stopProviderModelCatalogPolling);
  on(elements.specification, "input", () => updateRuntimeRunControls());
  on(elements.uploadSpecificationButton, "click", () => elements.specificationFileInput?.click());
  on(elements.specificationFileInput, "change", (event) => {
    const file = event.target?.files?.[0];
    loadSpecificationFromFile(file);
  });
  on(elements.runButton, "click", () => context.createSessionAndStart().catch(context.statusError));
  on(elements.stopButton, "click", (event) => {
    event.stopPropagation();
    context.stopActiveRun().catch(context.statusError);
  });
  on(elements.refreshRuns, "click", () => context.loadRuns().catch(context.statusError));
  on(elements.retryRunButton, "click", () => context.retrySelectedRun().catch(context.statusError));
  on(elements.resumeRunButton, "click", () => context.resumeSelectedRun().catch(context.statusError));
  on(elements.applyDecisionPatchesButton, "click", () => context.applySelectedDecisionPatches().catch(context.statusError));
  on(elements.runtimeHarnessSelect, "change", onRuntimeHarnessChanged);
  on(elements.providerSelect, "change", () => {
    onProviderChanged();
    refreshSelectedProviderModels({ force: false }).catch(() => {});
  });
  on(elements.modelSelect, "change", onModelSelectChanged);
  on(elements.modelRefreshButton, "click", () => refreshSelectedProviderModels({ force: true }).catch(() => {}));
  on(elements.modelInput, "input", onModelBindingChanged);

  on(elements.renameSessionButton, "pointerdown", (event) => {
    if (!context.sessionTitleEditing()) return;
    event.preventDefault();
    context.setSkipNextRenameSessionClick(true);
    context.cancelSessionTitleEdit();
  });
  on(elements.renameSessionButton, "click", () => {
    if (!context.selectedSessionId()) return;
    if (context.skipNextRenameSessionClick()) {
      context.setSkipNextRenameSessionClick(false);
      return;
    }
    if (context.sessionTitleEditing()) {
      context.cancelSessionTitleEdit();
    } else {
      context.beginSessionTitleEdit();
    }
  });
  on(elements.deleteSessionButton, "click", context.openDeleteSessionModal);
  on(elements.closeDeleteSessionModalButton, "click", () => {
    context.setDeleteSessionCandidateId("");
    elements.deleteSessionModal?.close();
  });
  on(elements.cancelDeleteSessionButton, "click", () => {
    context.setDeleteSessionCandidateId("");
    elements.deleteSessionModal?.close();
  });
  on(elements.deleteSessionModal, "close", () => context.setDeleteSessionCandidateId(""));
  on(elements.confirmDeleteSessionButton, "click", () => context.deleteSelectedSession().catch(context.statusError));
  on(elements.sessionTitleInput, "keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      context.commitSessionTitleEdit().catch(context.statusError);
    } else if (event.key === "Escape") {
      event.preventDefault();
      context.cancelSessionTitleEdit();
    }
  });
  on(elements.sessionTitleInput, "blur", () => {
    if (!context.sessionTitleEditing()) return;
    context.commitSessionTitleEdit().catch(context.statusError);
  });
}

export default bindSessionRunEvents;
