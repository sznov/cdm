import { els } from "./dom.js";
import { scheduleSessionRailWidthClamp } from "./layout.js";
import {
  sessionCustomTitle,
  sessionDisplayDate,
  sessionDisplaySubtitle,
  sessionDisplayTitle,
} from "./display.js";

export function renderSessionListView(options = {}) {
  const {
    isSessionActivelyRunning,
    lastAutoScrolledSessionId = "",
    onSessionSelected,
    selectedSessionId,
    sessionRecords = [],
  } = options;
  if (!els.sessionList) return lastAutoScrolledSessionId;
  els.sessionList.innerHTML = "";
  if (!sessionRecords.length) {
    const empty = document.createElement("div");
    empty.className = "session-empty";
    empty.textContent = "No sessions yet.";
    els.sessionList.append(empty);
    scheduleSessionRailWidthClamp();
    return "";
  }
  let selectedRow = null;
  let nextAutoScrolledSessionId = lastAutoScrolledSessionId;
  for (const session of sessionRecords) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "session-row";
    const normalizedStatus = session.status || "created";
    row.classList.add(`status-${normalizedStatus}`);
    const isSelected = session.session_id === selectedSessionId;
    const isActive = Boolean(isSessionActivelyRunning?.(session));
    if (isSelected) {
      row.classList.add("selected");
      row.setAttribute("aria-current", "page");
      selectedRow = row;
    }
    if (isActive) row.classList.add("is-active-run");
    const displayTitle = sessionDisplayTitle(session);
    const displayDate = sessionDisplayDate(session);
    const displaySubtitle =
      isSelected && displayTitle !== displayDate ? displayDate : sessionDisplaySubtitle(session);
    const hasCustomTitle = Boolean(sessionCustomTitle(session));
    row.setAttribute(
      "aria-label",
      `${displayTitle}${displaySubtitle ? ` ${displaySubtitle}` : ""} ${isSelected ? "selected " : ""}${isActive ? "running " : ""}${normalizedStatus}`
    );
    row.title = isActive ? "Running" : normalizedStatus;
    const title = document.createElement("strong");
    title.className = hasCustomTitle ? "session-title-custom" : "session-title-datetime";
    title.textContent = displayTitle;
    row.append(title);
    if (displaySubtitle) {
      const subtitle = document.createElement("span");
      subtitle.className = "session-title-datetime";
      subtitle.textContent = displaySubtitle;
      row.append(subtitle);
    }
    if (isActive) {
      const indicator = document.createElement("span");
      indicator.className = "session-progress-indicator";
      indicator.setAttribute("aria-hidden", "true");
      row.append(indicator);
    }
    row.addEventListener("click", () => onSessionSelected?.(session.session_id, session));
    els.sessionList.append(row);
  }
  if (selectedRow && selectedSessionId && nextAutoScrolledSessionId !== selectedSessionId) {
    nextAutoScrolledSessionId = selectedSessionId;
    requestAnimationFrame(() => {
      selectedRow.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
  }
  scheduleSessionRailWidthClamp();
  return nextAutoScrolledSessionId;
}
