export function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

export function optionalClone(value) {
  return value == null ? null : clone(value);
}

export function shortRunId(jobId) {
  const text = String(jobId || "");
  if (text.length <= 18) return text || "unknown";
  return `${text.slice(0, 13)}...${text.slice(-6)}`;
}

export function basenamePath(path) {
  const text = String(path || "").trim();
  if (!text) return "";
  const parts = text.split(/[\\/]+/).filter(Boolean);
  return parts[parts.length - 1] || text;
}

export function titleFromIdentifier(value) {
  return String(value || "runtime")
    .replace(/[_-]+/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (char) => char.toUpperCase());
}
