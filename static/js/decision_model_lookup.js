export function modelEntityNameById(model, entityId) {
  const entities = model?.entities || [];
  return entities.find((entity) => entity.entity_id === entityId)?.name || "";
}

export function modelEntityByNameOrId(model, entityRef) {
  const ref = String(entityRef || "").trim();
  if (!ref) return null;
  const entities = model?.entities || [];
  return entities.find((entity) => entity.name === ref || entity.entity_id === ref) || null;
}

export function modelEntityAttributeNames(model, entity, visited = new Set()) {
  if (!entity) return new Set();
  const key = entity.entity_id || entity.name || "";
  if (key && visited.has(key)) return new Set();
  if (key) visited.add(key);
  const names = new Set((entity.attributes || []).map((attribute) => attribute?.name).filter(Boolean));
  for (const parentRef of entity.inherits_from || []) {
    const parent = modelEntityByNameOrId(model, parentRef);
    for (const name of modelEntityAttributeNames(model, parent, visited)) names.add(name);
  }
  return names;
}

export function modelRelationshipByName(model, name) {
  const relationships = model?.relationships || [];
  return relationships.find((relationship) => relationship.name === name || relationship.relationship_id === name) || null;
}

export function relationshipEndpointNames(model, relationship) {
  if (!relationship) return { source: "", target: "" };
  if (relationship.source || relationship.target) {
    return {
      source: relationship.source?.entity || "",
      target: relationship.target?.entity || "",
    };
  }
  return {
    source: modelEntityNameById(model, relationship.source_entity_id),
    target: modelEntityNameById(model, relationship.target_entity_id),
  };
}

export function identifierContextEntityLabel(model, operation) {
  if (!operation || operation.op !== "setIdentifier") return "";
  const entity = operation.entity || "";
  const relationshipRef = (operation.parts || []).find((part) => part?.kind === "relationship" && part.ref)?.ref || "";
  if (!entity || !relationshipRef) return "";
  const relationship = modelRelationshipByName(model, relationshipRef);
  const endpoints = relationshipEndpointNames(model, relationship);
  if (endpoints.source === entity) return endpoints.target;
  if (endpoints.target === entity) return endpoints.source;
  return endpoints.target || endpoints.source || "";
}
