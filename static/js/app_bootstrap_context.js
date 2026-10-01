import { els } from './dom.js';
import {
  getAppConfig,
} from './runtime.js';
import {
  selectedGenerationOutput,
  selectedPlantuml,
  selectedPlantumlUrl,
  selectedStructuredModel,
  selectedWorkingModel,
  state,
} from './state.js';

export function createAppBootstrapContext(callbacks) {
  return {
    ...callbacks,
    elements: els,
    currentGenerationOutput: selectedGenerationOutput,
    currentPlantuml: selectedPlantuml,
    currentPlantumlUrl: selectedPlantumlUrl,
    currentStructuredModel: selectedStructuredModel,
    currentWorkingModel: selectedWorkingModel,
    defaultCorrectionTemplateId: () => getAppConfig().default_correction_template_id,
    pendingChatCorrection: () => state.pendingChatCorrection,
    runtimeHarness: () => state.runtimeHarness,
    selectedSessionId: () => state.selectedSessionId,
    sessionRecords: () => state.sessionRecords,
    sessionTitleEditing: () => state.sessionTitleEditing,
    setDeleteSessionCandidateId: (sessionId) => {
      state.deleteSessionCandidateId = sessionId || "";
    },
    setSkipNextRenameSessionClick: (skip) => {
      state.skipNextRenameSessionClick = Boolean(skip);
    },
    skipNextRenameSessionClick: () => state.skipNextRenameSessionClick,
  };
}
