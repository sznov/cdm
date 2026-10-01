import { ARTIFACT_ICON_SVGS } from "./icons_artifacts.js";
import { CHAT_ICON_SVGS } from "./icons_chat.js";
import { NAVIGATION_ICON_SVGS } from "./icons_navigation.js";
import { TRACE_ICON_SVGS } from "./icons_trace.js";

const ICON_SVGS = {
  ...NAVIGATION_ICON_SVGS,
  ...TRACE_ICON_SVGS,
  ...ARTIFACT_ICON_SVGS,
  ...CHAT_ICON_SVGS,
};

export function traceIconSvg(kind) {
  return ICON_SVGS[kind] || "";
}
