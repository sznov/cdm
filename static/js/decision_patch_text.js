export function cleanDecisionPatchText(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  const letters = text.replace(/[^A-Za-z]/g, "");
  const mostlyUpper = letters.length >= 4 && letters === letters.toUpperCase();
  if (!mostlyUpper) return text;
  const lowered = text.toLocaleLowerCase();
  return lowered.charAt(0).toLocaleUpperCase() + lowered.slice(1);
}

export function humanDecisionPatchKind(value, patch = {}) {
  const normalized = String(value || "").replace(/[_-]+/g, "").toLowerCase();
  if (!normalized) return "";
  const status = String(patch.status || "").toLowerCase();
  const hasOperation = Boolean(patch.operation);
  if (normalized.includes("assumption")) return hasOperation && status !== "noted" ? "Assumption option" : "Model assumption";
  if (normalized.includes("decision")) return hasOperation && status !== "noted" ? "Decision point" : "Model decision";
  if (normalized.includes("repair")) return "Repair";
  return cleanDecisionPatchText(String(value).replace(/([a-z])([A-Z])/g, "$1 $2"));
}

export function humanDecisionPatchStatus(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "noted") return "";
  if (normalized === "pending") return "Pending";
  if (normalized === "applied") return "Applied";
  if (normalized === "rejected") return "Rejected";
  return cleanDecisionPatchText(value);
}

export function humanDecisionPatchSource(value) {
  const normalized = String(value || "").toLowerCase();
  if (!normalized) return "";
  if (normalized === "draft_model_issue") return "Draft";
  if (normalized === "coverage_critic") return "Coverage critic";
  return cleanDecisionPatchText(String(value).replace(/[_-]+/g, " "));
}
