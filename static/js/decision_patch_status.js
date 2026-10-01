export function decisionPatchIsFinal(patch = {}) {
  return ["applied", "rejected", "noted"].includes(String(patch.status || "").toLowerCase());
}

export function decisionPatchRequiresChoice(patch = {}) {
  return Boolean(patch.operation) && !decisionPatchIsFinal(patch);
}

export function decisionPatchSortRank(patch = {}) {
  if (decisionPatchRequiresChoice(patch)) return 0;
  const kind = String(patch.kind || "").toLowerCase();
  const status = String(patch.status || "").toLowerCase();
  if (kind.includes("decision") && status !== "noted") return 1;
  if (kind.includes("assumption") && status !== "noted") return 2;
  if (status === "noted") return 4;
  return 3;
}

export function sortedDecisionPatches(patches = []) {
  return patches
    .map((patch, index) => ({ patch, index }))
    .sort((a, b) => decisionPatchSortRank(a.patch) - decisionPatchSortRank(b.patch) || a.index - b.index)
    .map((item) => item.patch);
}

export function decisionPatchHasDecisionPoint(patch = {}) {
  return Boolean(patch.operation) || decisionPatchRequiresChoice(patch);
}

export function decisionPatchIsAssumption(patch = {}) {
  const kind = String(patch.kind || "").toLowerCase();
  if (decisionPatchHasDecisionPoint(patch)) return false;
  if (kind.includes("assumption")) return true;
  if (kind.includes("decision")) return false;
  return !patch.operation;
}
