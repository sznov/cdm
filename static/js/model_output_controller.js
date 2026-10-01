import {
  jumpModelOutputToCurrent,
  updateModelOutputJump,
} from "./model_output_scroll_controller.js";
import {
  setModelOutputExpanded,
  toggleModelOutputExpanded,
} from "./model_output_expansion_controller.js";
import {
  appendText,
  setScrollableText,
} from "./model_output_text_updates.js";
import {
  ensureModelOutputBubble,
  modelOutputTextForDisplay,
  refreshModelOutputMarkdown,
  renderModelOutputMarkdown,
  scheduleModelOutputMarkdownRender,
  upsertTraceEntryChatBubble,
} from "./model_output_markdown_controller.js";
import {
  selectedGenerationOutput,
  selectedPresentationTrace,
  selectedWorkingModel,
  state,
} from './state.js';

export function bindModelOutputController(dependencies) {
  const context = {
    elements: dependencies.elements,
    currentGenerationOutput: selectedGenerationOutput,
    currentGenerationTraceId: () => state.currentGenerationTraceId,
    currentWorkingModel: selectedWorkingModel,
    modelOutputExpanded: () => state.modelOutputExpanded,
    renderSessionChat: dependencies.renderSessionChat,
    setModelOutputExpanded: (expanded) => {
      state.modelOutputExpanded = Boolean(expanded);
    },
    syncBuildLogModalCurrentOutput: dependencies.syncBuildLogModalCurrentOutput,
    traceEntries: selectedPresentationTrace,
  };
  return Object.freeze({
    appendText: (pre, text) => appendText(context, pre, text),
    ensureModelOutputBubble: () => ensureModelOutputBubble(context),
    jumpModelOutputToCurrent: () => jumpModelOutputToCurrent(context),
    modelOutputTextForDisplay: () => modelOutputTextForDisplay(context),
    refreshModelOutputMarkdown: () => refreshModelOutputMarkdown(context),
    renderModelOutputMarkdown: () => renderModelOutputMarkdown(context),
    scheduleModelOutputMarkdownRender: () => scheduleModelOutputMarkdownRender(context),
    setModelOutputExpanded: (expanded) => setModelOutputExpanded(context, expanded),
    setScrollableText: (pre, text, options = {}) => setScrollableText(context, pre, text, options),
    toggleModelOutputExpanded: () => toggleModelOutputExpanded(context),
    updateModelOutputJump: () => updateModelOutputJump(context),
    upsertTraceEntryChatBubble: (entry) => upsertTraceEntryChatBubble(context, entry),
  });
}
