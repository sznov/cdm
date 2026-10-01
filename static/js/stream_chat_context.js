import { runStateById, setRunOutput } from './state.js';

export function streamChatEventContext(context, generationActions = {}, runId) {
  const { state } = context;
  return {
    activeCorrectionStreamChatId: () => state.activeCorrectionStreamChatId,
    addTraceEntry: context.addTraceEntry,
    appendCorrectionChatMessage: context.appendCorrectionChatMessage,
    appendCurrentGeneration: generationActions.appendCurrentGeneration,
    appendQuestionChatMessage: context.appendQuestionChatMessage,
    completeCurrentGenerationStream: generationActions.completeCurrentGenerationStream,
    currentGenerationOutput: () => runStateById(runId)?.output || "",
    currentGenerationTraceId: () => state.currentGenerationTraceId,
    setActiveCorrectionStreamChatId: (chatId) => {
      state.activeCorrectionStreamChatId = chatId || "";
    },
    setCurrentGenerationOutput: (output) => {
      setRunOutput(runId, output);
    },
    setStatus: context.setStatus,
    startCurrentGenerationStream: generationActions.startCurrentGenerationStream,
    updateCorrectionChatControls: context.updateCorrectionChatControls,
    updateDecisionPatches: context.updateDecisionPatches,
    updateQuestionChatControls: context.updateQuestionChatControls,
    upsertCorrectionStreamChat: context.upsertCorrectionStreamChat,
  };
}
