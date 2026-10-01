import { isScrolledNearBottom } from "./chat_messages.js";
import {
  appendScrollableText,
  setScrollableTextContent,
} from "./scroll_text.js";
import { scheduleModelOutputMarkdownRender } from "./model_output_markdown_controller.js";
import { updateModelOutputJump } from "./model_output_scroll_controller.js";

function syncRawOutputDependents(context) {
  updateModelOutputJump(context);
  scheduleModelOutputMarkdownRender(context);
  context.syncBuildLogModalCurrentOutput();
}

export function setScrollableText(context, pre, text, options = {}) {
  if (!pre) return false;
  const follow = setScrollableTextContent(pre, text, {
    ...options,
    isScrolledNearBottom,
  });
  if (pre === context.elements.rawOutput) syncRawOutputDependents(context);
  return follow;
}

export function appendText(context, pre, text) {
  if (!pre) return false;
  const follow = appendScrollableText(pre, text, { isScrolledNearBottom });
  if (pre === context.elements.rawOutput) syncRawOutputDependents(context);
  return follow;
}
