export function modelCountsFromSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return null;
  const entities = Array.isArray(snapshot.entities) ? snapshot.entities.length : null;
  const attributes = Array.isArray(snapshot.entities)
    ? snapshot.entities.reduce((sum, entity) => sum + (Array.isArray(entity?.attributes) ? entity.attributes.length : 0), 0)
    : null;
  const relationships = Array.isArray(snapshot.relationships) ? snapshot.relationships.length : null;
  if (entities == null && attributes == null && relationships == null) return null;
  return {
    entities: entities ?? 0,
    attributes: attributes ?? 0,
    relationships: relationships ?? 0,
  };
}

export function checkpointCounts(entry, modelSnapshotForEntry = () => null) {
  if (!entry) return null;
  const payload = entry.payload || {};
  if (Number.isFinite(Number(payload.entity_count)) || Number.isFinite(Number(payload.relationship_count))) {
    const snapshotCounts = modelCountsFromSnapshot(modelSnapshotForEntry(entry));
    return {
      entities: Number(payload.entity_count || 0),
      attributes: snapshotCounts?.attributes ?? 0,
      relationships: Number(payload.relationship_count || 0),
    };
  }
  return modelCountsFromSnapshot(modelSnapshotForEntry(entry));
}

export function numericPayloadValue(payload, keys) {
  for (const key of keys) {
    const value = payload?.[key];
    if (Array.isArray(value)) return value.length;
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  }
  return null;
}

export function checkpointOperationCounts(entry) {
  if (!entry) return null;
  const payload = entry.payload || {};
  let accepted = numericPayloadValue(payload, [
    "accepted_operation_count",
    "accepted_count",
    "accepted_ops_count",
    "applied_operations",
    "already_satisfied_operations",
    "accepted",
  ]);
  let rejected = numericPayloadValue(payload, [
    "rejected_operation_count",
    "rejected_count",
    "rejected_ops_count",
    "rejected_operations",
    "rejected",
  ]);
  const deferred = numericPayloadValue(payload, ["deferred_count", "deferred"]);
  if (rejected == null && deferred != null) rejected = deferred;
  else if (deferred != null) rejected += deferred;
  const summaryText = String(entry.summary || payload.summary || "");
  if (accepted == null) {
    const match = summaryText.match(/(\d+)\s+accepted\b/i);
    if (match) accepted = Number(match[1]);
  }
  if (rejected == null) {
    const match = summaryText.match(/(\d+)\s+rejected\b/i);
    if (match) rejected = Number(match[1]);
  }
  if (accepted == null && rejected == null) return null;
  return {
    accepted: accepted ?? 0,
    rejected: rejected ?? 0,
  };
}
