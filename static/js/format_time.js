export function traceEventTimestamp(payload = {}) {
  return typeof payload.__trace_timestamp_utc === "string"
    ? payload.__trace_timestamp_utc.trim()
    : "";
}

export function traceTimestamp(payload = {}) {
  return traceEventTimestamp(payload) || new Date().toISOString();
}

export function formatLocalTime(utcValue) {
  if (!utcValue) return "unknown time";
  const date = new Date(utcValue);
  if (Number.isNaN(date.getTime())) return String(utcValue);
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function pad2(value) {
  return String(value).padStart(2, "0");
}

export function formatCompactLocalTime(utcValue) {
  if (!utcValue) return "unknown";
  const date = new Date(utcValue);
  if (Number.isNaN(date.getTime())) return String(utcValue);
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
}

export function formatTraceDelta(previous, current) {
  if (!previous?.created_at || !current?.created_at) return "";
  const previousMs = new Date(previous.created_at).getTime();
  const currentMs = new Date(current.created_at).getTime();
  if (Number.isNaN(previousMs) || Number.isNaN(currentMs) || currentMs < previousMs) return "";
  const delta = currentMs - previousMs;
  if (delta < 1000) return `+${delta}ms`;
  if (delta < 60000) return `+${(delta / 1000).toFixed(delta < 10000 ? 1 : 0)}s`;
  const minutes = Math.floor(delta / 60000);
  const seconds = Math.round((delta % 60000) / 1000);
  return `+${minutes}m ${seconds}s`;
}
