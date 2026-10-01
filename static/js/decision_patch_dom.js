export function decisionOptionDomId(value) {
  return String(value || "decision")
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48) || "decision";
}
