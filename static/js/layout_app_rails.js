import { configureAppRailDependencies } from "./layout_app_rail_config.js";

export {
  appRailCollapsed,
} from "./layout_app_rail_dom.js";
export {
  applyAppRailWidth,
  clampAppRailWidths,
  currentAppRailWidth,
  resizeAppRailBy,
  scheduleSessionRailWidthClamp,
} from "./layout_app_rail_width.js";
export {
  restoreAppRailLayout,
  setAppRailCollapsed,
  toggleAppRail,
} from "./layout_app_rail_collapse.js";
export {
  CHAT_RAIL_DRAG_COLLAPSE_THRESHOLD,
  SESSION_RAIL_DRAG_COLLAPSE_THRESHOLD,
} from "./layout_app_rail_state.js";

export function configureAppRails(options = {}) {
  configureAppRailDependencies(options);
}
