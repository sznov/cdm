import { els } from './dom.js';
import {
  selectedCorrectionTemplate,
} from './correction_templates.js';
import {
  getAppConfig,
} from './runtime.js';
import {
  beginRunOperation,
  finishRunOperation,
  selectRun,
  state,
} from './state.js';

export function createActionFlowContext(callbacks) {
  return {
    ...callbacks,
    elements: els,
    beginRunOperation,
    selectedRunId: () => state.selectedRunId,
    selectedSessionId: () => state.selectedSessionId,
    defaultCorrectionTemplateId: () => getAppConfig().default_correction_template_id,
    selectedCorrectionTemplate,
    finishRunOperation,
    setSelectedRunId: (runId) => {
      selectRun(runId);
    },
    startCorrectionStreamChat: () => {
      state.activeCorrectionStreamChatId = `correction-stream-${Date.now()}`;
    },
    clearCorrectionStreamChat: () => {
      state.activeCorrectionStreamChatId = "";
    },
  };
}
