export function decisionOperationName(operation = {}) {
  return String(operation?.op || operation?.type || operation?.operation || "").trim();
}

export function decisionOperationEntity(operation = {}) {
  const raw =
    operation?.entity ||
    operation?.target_entity ||
    operation?.targetEntity ||
    operation?.target?.entity ||
    operation?.source?.entity ||
    "";
  return String(raw || "").trim();
}

export function decisionOperationConflictKey(operation = {}) {
  if (!operation || typeof operation !== "object") return "";
  const op = decisionOperationName(operation).toLowerCase();
  const entity = decisionOperationEntity(operation);
  if (!entity) return "";
  if (op === "setidentifier" || (op.includes("identifier") && op.includes("set"))) return `identifier:${entity}`;
  return "";
}

export function decisionPatchConflictKey(patch = {}, option = null) {
  return (
    decisionOperationConflictKey(option?.operation || null) ||
    decisionOperationConflictKey(patch.operation || null) ||
    ""
  );
}
