import {
  runStateById,
  setRunOutput,
} from './state.js';

export function generationStreamContext(context, runId) {
  const { state } = context;
  return {
    elements: context.elements,
    traceEntries: runStateById(runId)?.presentationTrace || [],
    getTraceId: () => state.currentGenerationTraceId,
    setTraceId: (id) => {
      state.currentGenerationTraceId = id;
    },
    getOutput: () => runStateById(runId)?.output || "",
    setOutput: (output) => {
      setRunOutput(runId, output);
    },
    getSelectedTraceId: () => state.selectedTraceId,
    addTraceEntry: context.addTraceEntry,
    appendText: context.appendText,
    scheduleModelOutputMarkdownRender: context.scheduleModelOutputMarkdownRender,
    setScrollableText: context.setScrollableText,
    setStatus: context.setStatus,
    updateTraceEntry: context.updateTraceEntry,
    updateTraceInspectorDetail: context.updateTraceInspectorDetail,
    upsertTraceEntryChatBubble: context.upsertTraceEntryChatBubble,
  };
}
