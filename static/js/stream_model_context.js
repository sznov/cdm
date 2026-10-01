import { runStateById, setRunOutput } from './state.js';

export function streamModelEventContext(context, generationActions = {}, runId) {
  const { state } = context;
  return {
    elements: context.elements,
    addTraceEntry: context.addTraceEntry,
    applyModelSnapshotPayload: (payload) => context.applyModelSnapshotPayload(runId, payload),
    currentDecisionPatches: () => state.currentDecisionPatches,
    currentGenerationOutput: () => runStateById(runId)?.output || "",
    markCurrentGenerationInterrupted: generationActions.markCurrentGenerationInterrupted,
    setCurrentGenerationOutput: (output) => {
      setRunOutput(runId, output);
    },
    setScrollableText: context.setScrollableText,
    setStatus: context.setStatus,
    updateDecisionPatches: context.updateDecisionPatches,
  };
}
