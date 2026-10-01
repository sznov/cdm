import { cleanDecisionPatchText } from "./decision_patch_text.js";
import { identifierContextEntityLabel } from "./decision_model_lookup.js";

export function decisionPatchApplyLabel(patch = {}, operationOverride = null, model = null) {
  const operation = operationOverride || patch.operation || {};
  if (operation.op === "setIdentifier") {
    const entity = operation.entity || "";
    const parts = Array.isArray(operation.parts) ? operation.parts : [];
    const relationshipRefs = parts.filter((part) => part?.kind === "relationship" && part.ref).map((part) => part.ref);
    const partRefs = parts
      .filter((part) => part?.ref)
      .map((part) => part.ref);
    const contextEntity = identifierContextEntityLabel(model, operation);
    if (entity && partRefs.length > 1) return `set ${entity} identifier to ${partRefs.join(", ")}`;
    if (entity && relationshipRefs.length === 1 && contextEntity) {
      return `add ${contextEntity} (${relationshipRefs[0]}) to ${entity} identifier`;
    }
    if (entity && relationshipRefs.length) return `add ${relationshipRefs.join(", ")} to ${entity} identifier`;
    if (entity) return `set ${entity} identifier`;
  }
  return cleanDecisionPatchText(patch.apply_label || patch.title || "apply patch");
}
