import { els } from "./dom.js";
import { scheduleHeaderOverflowUpdate } from "./header_overflow_menu.js";

let headerOverflowObserver = null;

export function setupHeaderLayoutObserver() {
  if (!("ResizeObserver" in window) || headerOverflowObserver) return;
  headerOverflowObserver = new ResizeObserver(scheduleHeaderOverflowUpdate);
  const sessionHeader = document.querySelector(".session-header");
  if (sessionHeader) headerOverflowObserver.observe(sessionHeader);
  if (els.sessionTitle) headerOverflowObserver.observe(els.sessionTitle);
  if (els.runArchiveSummary) headerOverflowObserver.observe(els.runArchiveSummary);
}
