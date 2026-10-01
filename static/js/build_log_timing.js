import {
  formatLocalTime,
  pad2,
} from "./format_time.js";

function parsedTimestamp(value) {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text) return null;
  const date = new Date(text);
  return Number.isNaN(date.getTime()) ? null : { date, text };
}

function localClockText(date) {
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
}

export function buildLogDurationText(durationMs) {
  if (!Number.isFinite(durationMs) || durationMs < 0) return "";
  if (durationMs > 0 && durationMs < 1000) return "<1s";
  const totalSeconds = Math.floor(durationMs / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  if (totalSeconds < 3600) {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
  }
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
}

export function buildLogTimingPresentation(startedAtUtc, completedAtUtc = "", options = {}) {
  const started = parsedTimestamp(startedAtUtc);
  if (!started) return null;
  const completed = parsedTimestamp(completedAtUtc);
  const durationMs = completed ? completed.date.getTime() - started.date.getTime() : null;
  const duration = durationMs != null && durationMs >= 0 ? buildLogDurationText(durationMs) : "";
  const interval = options.kind === "interval";
  const hasCompletedInterval = interval && Boolean(duration) && Boolean(completed);
  const displayed = hasCompletedInterval && completed ? completed : started;
  const clock = localClockText(displayed.date);
  const eventLabel = interval ? "Started" : "Event";
  const title = [
    `${eventLabel}: ${formatLocalTime(started.text)} local`,
    `${eventLabel} UTC: ${started.text}`,
  ];
  if (duration) {
    title.push(
      `Completed: ${formatLocalTime(completed.text)} local`,
      `Completed UTC: ${completed.text}`,
      `Duration: ${duration}`,
    );
  }
  return {
    ariaLabel: interval
      ? (hasCompletedInterval
        ? `Completed at ${clock}; duration ${duration}`
        : `Started at ${clock}`)
      : `Event time ${clock}`,
    clock,
    datetime: displayed.text,
    duration,
    text: duration ? `${duration} · ${clock}` : clock,
    title: title.join("\n"),
  };
}

export function createBuildLogTimeElement(startedAtUtc, completedAtUtc = "", options = {}) {
  const timing = buildLogTimingPresentation(startedAtUtc, completedAtUtc, options);
  if (!timing) return null;
  const element = document.createElement("time");
  element.className = "build-log-time";
  element.classList.toggle("has-duration", Boolean(timing.duration));
  element.dateTime = timing.datetime;
  element.title = timing.title;
  element.setAttribute("aria-label", timing.ariaLabel);
  const duration = document.createElement("span");
  duration.className = "build-log-duration";
  duration.textContent = timing.duration;
  duration.setAttribute("aria-hidden", "true");
  const separator = document.createElement("span");
  separator.className = "build-log-time-separator";
  separator.textContent = timing.duration ? " · " : "";
  separator.setAttribute("aria-hidden", "true");
  const clock = document.createElement("span");
  clock.className = "build-log-clock";
  clock.textContent = timing.clock;
  clock.setAttribute("aria-hidden", "true");
  element.append(duration, separator, clock);
  return element;
}
