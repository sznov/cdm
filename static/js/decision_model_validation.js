import {
  modelEntityAttributeNames,
  modelEntityByNameOrId,
  modelRelationshipByName,
  relationshipEndpointNames,
} from "./decision_model_lookup.js";

export function decisionOperationValidationIssue(operation, model) {
  if (!operation || typeof operation !== "object") return "";
  if (!model?.entities?.length) return "";
  const op = String(operation.op || "");
  const entityRef = operation.entity || operation.source?.entity || operation.target?.entity || "";
  if (entityRef && !modelEntityByNameOrId(model, entityRef)) return `Missing entity: ${entityRef}`;
  if (op === "setIdentifier") {
    const entity = modelEntityByNameOrId(model, operation.entity);
    if (!entity) return `Missing entity: ${operation.entity || ""}`;
    const entityName = entity.name || operation.entity || "";
    const attributeNames = modelEntityAttributeNames(model, entity);
    for (const part of operation.parts || []) {
      const kind = String(part?.kind || "");
      const ref = String(part?.ref || "").trim();
      if (!ref) continue;
      if (kind === "attribute" && !attributeNames.has(ref) && ref !== "id") return `Missing attribute on ${entityName}: ${ref}`;
      if (kind === "relationship") {
        const relationship = modelRelationshipByName(model, ref);
        if (!relationship) return `Missing relationship: ${ref}`;
        const endpoints = relationshipEndpointNames(model, relationship);
        if (endpoints.source !== entityName && endpoints.target !== entityName) {
          return `Relationship ${ref} does not touch ${entityName}`;
        }
      }
    }
  }
  if (op === "removeRelationship" && operation.name && !modelRelationshipByName(model, operation.name)) {
    return `Missing relationship: ${operation.name}`;
  }
  if (op === "addRelationship") {
    const sourceEntity = operation.source?.entity;
    const targetEntity = operation.target?.entity;
    if (sourceEntity && !modelEntityByNameOrId(model, sourceEntity)) return `Missing source entity: ${sourceEntity}`;
    if (targetEntity && !modelEntityByNameOrId(model, targetEntity)) return `Missing target entity: ${targetEntity}`;
  }
  if ((op === "addAttribute" || op === "removeAttribute") && operation.entity && !modelEntityByNameOrId(model, operation.entity)) {
    return `Missing entity: ${operation.entity}`;
  }
  if (op === "removeAttribute") {
    const entity = modelEntityByNameOrId(model, operation.entity);
    const name = operation.name || operation.attribute || operation.ref;
    if (entity && name && !modelEntityAttributeNames(model, entity).has(name)) return `Missing attribute on ${entity.name}: ${name}`;
  }
  return "";
}
