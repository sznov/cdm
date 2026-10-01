import { configureAppRails } from "./layout_app_rails.js";

export {
  appRailCollapsed,
  clampAppRailWidths,
  resizeAppRailBy,
  restoreAppRailLayout,
  scheduleSessionRailWidthClamp,
  setAppRailCollapsed,
  toggleAppRail,
} from "./layout_app_rails.js";
export { beginAppRailResize } from "./layout_app_rail_resize.js";
export {
  closeCompactSessions,
  compactSessionsOpen,
  toggleCompactSessions,
} from "./layout_compact_sessions.js";

export function configureLayout(options = {}) {
  configureAppRails(options);
}
