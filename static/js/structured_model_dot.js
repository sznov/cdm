// @ts-check

/** @typedef {import("../../frontend/src/run_contracts.js").StructuredAttribute} StructuredAttribute */
/** @typedef {import("../../frontend/src/run_contracts.js").StructuredAttributeType} StructuredAttributeType */
/** @typedef {import("../../frontend/src/run_contracts.js").StructuredEntity} StructuredEntity */
/** @typedef {import("../../frontend/src/run_contracts.js").StructuredIdentifierPart} StructuredIdentifierPart */
/** @typedef {import("../../frontend/src/run_contracts.js").StructuredIdentifierPartKind} StructuredIdentifierPartKind */
/** @typedef {import("../../frontend/src/run_contracts.js").StructuredModel} StructuredModel */
/** @typedef {import("../../frontend/src/run_contracts.js").StructuredMultiplicity} StructuredMultiplicity */
/** @typedef {import("../../frontend/src/run_contracts.js").StructuredRelationship} StructuredRelationship */
/** @typedef {import("../../frontend/src/run_contracts.js").StructuredRelationshipEnd} StructuredRelationshipEnd */

const ATTRIBUTE_TYPES = new Set(["string", "int", "real", "bool", "date"]);
const IDENTIFIER_KINDS = new Set(["attribute", "relationship"]);
const MULTIPLICITIES = new Set(["0..1", "1", "0..*", "*", "1..*"]);

const TYPE_LABELS = Object.freeze({
  string: "String",
  int: "Integer",
  real: "Real",
  bool: "Boolean",
  date: "Date",
});

const THEMES = Object.freeze({
  light: Object.freeze({
    nodeBorder: "#475569",
    nodeFill: "#ffffff",
    text: "#111827",
    edge: "#475569",
  }),
  dark: Object.freeze({
    nodeBorder: "#94a3b8",
    nodeFill: "#1b1b1b",
    text: "#e5e7eb",
    edge: "#cbd5e1",
  }),
});

export class StructuredModelDiagramError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "StructuredModelDiagramError";
  }
}

/** @param {unknown} value @returns {value is Record<string, unknown>} */
function isPlainObject(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

/** @param {string} path @param {string} detail @returns {never} */
function invalid(path, detail) {
  throw new StructuredModelDiagramError(`Invalid structured model at ${path}: ${detail}`);
}

/**
 * @param {unknown} value
 * @param {string} path
 * @returns {Record<string, unknown>}
 */
function requireObject(value, path) {
  if (!isPlainObject(value)) invalid(path, "expected an object.");
  return value;
}

/**
 * @param {Record<string, unknown>} value
 * @param {readonly string[]} allowed
 * @param {string} path
 */
function rejectExtraKeys(value, allowed, path) {
  const allowedKeys = new Set(allowed);
  const extra = Object.keys(value).filter((key) => !allowedKeys.has(key)).sort(compareStrings);
  if (extra.length) invalid(path, `unexpected field${extra.length === 1 ? "" : "s"}: ${extra.join(", ")}.`);
}

/**
 * @param {unknown} value
 * @param {string} path
 * @param {{nullable?: boolean, nonempty?: boolean}} [options]
 * @returns {string | null}
 */
function requireString(value, path, options = {}) {
  if ((value === null || value === undefined) && options.nullable) return null;
  if (typeof value !== "string") invalid(path, "expected a string.");
  if (options.nonempty && !value.trim()) invalid(path, "must not be empty.");
  return value;
}

/** @param {unknown} value @param {string} path @returns {string} */
function requireNonemptyString(value, path) {
  const text = requireString(value, path, { nonempty: true });
  if (text === null) invalid(path, "expected a string.");
  return text;
}

/**
 * @param {unknown} value
 * @param {string} path
 * @returns {unknown[]}
 */
function requireArray(value, path) {
  if (!Array.isArray(value)) invalid(path, "expected an array.");
  return value;
}

/**
 * Mirror the backend's optional-list defaults without accepting a different
 * semantic shape for fields that are required on StructuredModel itself.
 *
 * @param {unknown} value
 * @param {string} path
 * @returns {unknown[]}
 */
function optionalArray(value, path) {
  if (value === null || value === undefined) return [];
  return requireArray(value, path);
}

/** @param {string} left @param {string} right */
function compareStrings(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

/** @param {readonly string[]} left @param {readonly string[]} right */
function compareStringTuples(left, right) {
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    const comparison = compareStrings(left[index] ?? "", right[index] ?? "");
    if (comparison) return comparison;
  }
  return 0;
}

/** @param {unknown} value @param {string} path @returns {StructuredAttribute} */
function normalizeAttribute(value, path) {
  const source = requireObject(value, path);
  rejectExtraKeys(source, ["name", "type"], path);
  const name = requireNonemptyString(source.name, `${path}.name`);
  const type = requireNonemptyString(source.type, `${path}.type`);
  if (!ATTRIBUTE_TYPES.has(type)) invalid(`${path}.type`, `unsupported attribute type '${type}'.`);
  return { name, type: /** @type {StructuredAttributeType} */ (type) };
}

/** @param {unknown} value @param {string} path @returns {StructuredIdentifierPart} */
function normalizeIdentifierPart(value, path) {
  const source = requireObject(value, path);
  rejectExtraKeys(source, ["kind", "ref"], path);
  const kind = requireNonemptyString(source.kind, `${path}.kind`);
  if (!IDENTIFIER_KINDS.has(kind)) invalid(`${path}.kind`, `unsupported identifier kind '${kind}'.`);
  return {
    kind: /** @type {StructuredIdentifierPartKind} */ (kind),
    ref: requireNonemptyString(source.ref, `${path}.ref`),
  };
}

/** @param {unknown} value @param {string} path @returns {StructuredEntity} */
function normalizeEntity(value, path) {
  const source = requireObject(value, path);
  rejectExtraKeys(source, ["name", "attributes", "identifier", "inherits_from"], path);
  const attributes = optionalArray(source.attributes, `${path}.attributes`)
    .map((attribute, index) => normalizeAttribute(attribute, `${path}.attributes[${index}]`))
    .sort((left, right) => compareStringTuples([left.name, left.type], [right.name, right.type]));
  const attributeNames = new Set();
  for (const attribute of attributes) {
    if (attributeNames.has(attribute.name)) invalid(path, `duplicate attribute name '${attribute.name}'.`);
    attributeNames.add(attribute.name);
  }

  const identifier = optionalArray(source.identifier, `${path}.identifier`)
    .map((part, index) => normalizeIdentifierPart(part, `${path}.identifier[${index}]`));
  const inheritsFrom = optionalArray(source.inherits_from, `${path}.inherits_from`)
    .map((parent, index) => requireNonemptyString(parent, `${path}.inherits_from[${index}]`));
  const inheritedParentNames = new Set();
  for (const parentName of inheritsFrom) {
    if (inheritedParentNames.has(parentName)) invalid(path, `duplicate inheritance parent '${parentName}'.`);
    inheritedParentNames.add(parentName);
  }

  return {
    name: requireNonemptyString(source.name, `${path}.name`),
    attributes,
    identifier,
    inherits_from: inheritsFrom,
  };
}

/** @param {unknown} value @param {string} path @returns {StructuredRelationshipEnd} */
function normalizeRelationshipEnd(value, path) {
  const source = requireObject(value, path);
  rejectExtraKeys(source, ["entity", "multiplicity", "role"], path);
  const rawMultiplicity = requireString(source.multiplicity, `${path}.multiplicity`, { nullable: true });
  if (rawMultiplicity !== null && !MULTIPLICITIES.has(rawMultiplicity)) {
    invalid(`${path}.multiplicity`, `unsupported multiplicity '${rawMultiplicity}'.`);
  }
  return {
    entity: requireNonemptyString(source.entity, `${path}.entity`),
    multiplicity: rawMultiplicity === "*"
      ? "0..*"
      : /** @type {StructuredMultiplicity | null} */ (rawMultiplicity),
    role: requireString(source.role, `${path}.role`, { nullable: true }),
  };
}

/** @param {unknown} value @param {string} path @returns {StructuredRelationship} */
function normalizeRelationship(value, path) {
  const source = requireObject(value, path);
  rejectExtraKeys(source, ["name", "source", "target"], path);
  return {
    name: requireString(source.name, `${path}.name`, { nullable: true }),
    source: normalizeRelationshipEnd(source.source, `${path}.source`),
    target: normalizeRelationshipEnd(source.target, `${path}.target`),
  };
}

/** @param {StructuredRelationship} relationship */
function relationshipSortTuple(relationship) {
  return [
    relationship.name ?? "",
    relationship.source.entity,
    relationship.source.multiplicity ?? "",
    relationship.source.role ?? "",
    relationship.target.entity,
    relationship.target.multiplicity ?? "",
    relationship.target.role ?? "",
  ];
}

/**
 * @param {StructuredModel} model
 * Match collect_entity_attribute_map: own attributes win, then parent
 * attributes fill gaps in declared parent order.
 *
 * @returns {Map<string, Map<string, StructuredAttribute>>}
 */
function inheritedAttributes(model) {
  const entities = new Map(model.entities.map((entity) => [entity.name, entity]));
  /** @type {Map<string, Map<string, StructuredAttribute>>} */
  const cache = new Map();

  /** @param {string} entityName @param {Set<string>} [visiting] @returns {Map<string, StructuredAttribute>} */
  function collect(entityName, visiting = new Set()) {
    const cached = cache.get(entityName);
    if (cached) return cached;
    if (visiting.has(entityName)) invalid("$.entities", `inheritance cycle includes '${entityName}'.`);
    const entity = entities.get(entityName);
    if (!entity) invalid("$.entities", `missing inherited entity '${entityName}'.`);
    const nextVisiting = new Set(visiting);
    nextVisiting.add(entityName);
    const attributes = new Map(entity.attributes.map((attribute) => [attribute.name, attribute]));
    for (const parentName of entity.inherits_from) {
      if (parentName === entityName) invalid("$.entities", `entity '${entityName}' cannot inherit from itself.`);
      for (const [name, attribute] of collect(parentName, nextVisiting)) {
        if (!attributes.has(name)) attributes.set(name, attribute);
      }
    }
    cache.set(entityName, attributes);
    return attributes;
  }

  for (const entity of model.entities) collect(entity.name);
  return cache;
}

/**
 * Validate identifier references and return the identifying child for every
 * relationship used as a composition edge.
 *
 * @param {StructuredModel} model
 * @returns {Map<StructuredRelationship, string>}
 */
function identifyingRelationshipChildren(model) {
  const attributesByEntity = inheritedAttributes(model);
  /** @type {Map<StructuredRelationship, string>} */
  const children = new Map();

  for (const entity of model.entities) {
    for (const part of entity.identifier) {
      if (part.kind === "attribute") {
        if (!attributesByEntity.get(entity.name)?.has(part.ref)) {
          invalid(
            `$.entities['${entity.name}'].identifier`,
            `attribute identifier '${part.ref}' does not resolve on that entity or its ancestors.`,
          );
        }
        continue;
      }

      const named = model.relationships.filter((relationship) => relationship.name === part.ref);
      const matches = named.filter((relationship) => (
        relationship.source.entity === entity.name || relationship.target.entity === entity.name
      ));
      if (!named.length) {
        invalid(`$.entities['${entity.name}'].identifier`, `relationship '${part.ref}' does not exist.`);
      }
      if (!matches.length) {
        invalid(
          `$.entities['${entity.name}'].identifier`,
          `relationship '${part.ref}' does not include that entity.`,
        );
      }
      if (matches.length > 1) {
        invalid(
          `$.entities['${entity.name}'].identifier`,
          `relationship '${part.ref}' is ambiguous for that entity.`,
        );
      }
      const relationship = matches[0];
      if (relationship.source.entity === relationship.target.entity) {
        invalid(
          `$.entities['${entity.name}'].identifier`,
          `self-relationship '${part.ref}' cannot identify its parent endpoint.`,
        );
      }
      const existingChild = children.get(relationship);
      if (existingChild && existingChild !== entity.name) {
        invalid(
          "$.entities",
          `relationship '${part.ref}' cannot identify both '${existingChild}' and '${entity.name}'.`,
        );
      }
      children.set(relationship, entity.name);
    }
  }
  return children;
}

/**
 * Validate an untrusted structured-model payload and return a detached,
 * deterministically ordered canonical model suitable for local rendering.
 *
 * @param {unknown} value
 * @returns {StructuredModel}
 */
export function normalizeStructuredModel(value) {
  const source = requireObject(value, "$");
  rejectExtraKeys(source, ["entities", "relationships"], "$");
  const entities = requireArray(source.entities, "$.entities")
    .map((entity, index) => normalizeEntity(entity, `$.entities[${index}]`))
    .sort((left, right) => compareStrings(left.name, right.name));
  const relationships = requireArray(source.relationships, "$.relationships")
    .map((relationship, index) => normalizeRelationship(relationship, `$.relationships[${index}]`))
    .sort((left, right) => compareStringTuples(relationshipSortTuple(left), relationshipSortTuple(right)));

  const entityNames = new Set();
  for (const entity of entities) {
    if (entityNames.has(entity.name)) invalid("$.entities", `duplicate entity name '${entity.name}'.`);
    entityNames.add(entity.name);
  }
  for (const entity of entities) {
    for (const parentName of entity.inherits_from) {
      if (!entityNames.has(parentName)) {
        invalid(`$.entities['${entity.name}'].inherits_from`, `missing parent entity '${parentName}'.`);
      }
    }
  }
  for (const [index, relationship] of relationships.entries()) {
    if (!entityNames.has(relationship.source.entity)) {
      invalid(`$.relationships[${index}].source.entity`, `missing entity '${relationship.source.entity}'.`);
    }
    if (!entityNames.has(relationship.target.entity)) {
      invalid(`$.relationships[${index}].target.entity`, `missing entity '${relationship.target.entity}'.`);
    }
  }

  const model = { entities, relationships };
  identifyingRelationshipChildren(model);
  return model;
}

/** @param {string} value */
function escapeDotString(value) {
  return value
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\r\n|\r|\n/g, "\\n")
    .replace(/\t/g, "\\t")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, (character) => (
      `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`
    ));
}

/** @param {string} value */
function quoted(value) {
  return `"${escapeDotString(value)}"`;
}

/** @param {unknown} value @param {"LEFT" | "CENTER"} [lineAlignment] */
function escapeHtmlLabelText(value, lineAlignment = "LEFT") {
  const normalized = String(value ?? "")
    .replace(/\r\n|\r/g, "\n")
    .replace(/\t/g, "    ")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, "�");
  return normalized
    .split("\n")
    .map((line) => line
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;"))
    .join(`<BR ALIGN="${lineAlignment}"/>`);
}

/**
 * @param {StructuredEntity} entity
 * @param {Map<string, StructuredAttribute>} attributes
 */
function identifierMethodLabel(entity, attributes) {
  const attributeParts = entity.identifier.filter((part) => part.kind === "attribute");
  if (!attributeParts.length) return "";
  const relationshipIdentifier = entity.identifier.some((part) => part.kind === "relationship");
  const signature = attributeParts.map((part) => {
    const attribute = attributes.get(part.ref);
    if (!attribute) {
      invalid(
        `$.entities['${entity.name}'].identifier`,
        `attribute identifier '${part.ref}' does not resolve on that entity or its ancestors.`,
      );
    }
    return `${part.ref}: ${TYPE_LABELS[attribute.type]}`;
  }).join(", ");
  return `${relationshipIdentifier ? "PK_D" : "PK"}(${signature})`;
}

/**
 * @param {StructuredEntity} entity
 * @param {Map<string, StructuredAttribute>} attributes
 * @param {{nodeBorder: string, nodeFill: string, text: string}} theme
 */
function entityHtmlLabel(entity, attributes, theme) {
  const rows = [
    `<TR><TD ALIGN="CENTER" CELLPADDING="7"><FONT FACE="Arial" POINT-SIZE="12" COLOR="${theme.text}"><B>${escapeHtmlLabelText(entity.name, "CENTER")}</B></FONT></TD></TR>`,
  ];
  if (entity.attributes.length) {
    const attributeText = entity.attributes
      .map((attribute) => `${escapeHtmlLabelText(attribute.name)}: ${TYPE_LABELS[attribute.type]}`)
      .join('<BR ALIGN="LEFT"/>');
    rows.push(
      `<TR><TD ALIGN="LEFT" BALIGN="LEFT" BORDER="1" SIDES="T" CELLPADDING="7"><FONT FACE="Arial" POINT-SIZE="11" COLOR="${theme.text}">${attributeText}</FONT></TD></TR>`,
    );
  }
  const identifierMethod = identifierMethodLabel(entity, attributes);
  if (identifierMethod) {
    rows.push(
      `<TR><TD ALIGN="LEFT" BALIGN="LEFT" BORDER="1" SIDES="T" CELLPADDING="7"><FONT FACE="Arial" POINT-SIZE="11" COLOR="${theme.text}">${escapeHtmlLabelText(identifierMethod)}</FONT></TD></TR>`,
    );
  }
  return `<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0" COLOR="${theme.nodeBorder}" BGCOLOR="${theme.nodeFill}" STYLE="ROUNDED">${rows.join("")}</TABLE>`;
}

/** @param {StructuredRelationshipEnd} end */
function relationshipEndLabel(end) {
  return end.multiplicity || "";
}

/**
 * @param {readonly [string, string][]} attributes
 */
function dotAttributes(attributes) {
  return `[${attributes.map(([name, value]) => `${name}=${quoted(value)}`).join(", ")}]`;
}

/**
 * Convert the canonical structured model into deterministic DOT. Model text
 * appears only in escaped HTML text or quoted labels; graph/node identifiers
 * are generated locally.
 *
 * @param {unknown} value
 * @param {{theme?: "light" | "dark"}} [options]
 * @returns {string}
 */
export function structuredModelToDot(value, options = {}) {
  const model = normalizeStructuredModel(value);
  const themeName = options.theme ?? "light";
  if (themeName !== "light" && themeName !== "dark") {
    throw new StructuredModelDiagramError(`Unsupported diagram theme '${String(themeName)}'.`);
  }
  const theme = THEMES[themeName];
  const identifyingChildren = identifyingRelationshipChildren(model);
  const attributesByEntity = inheritedAttributes(model);
  const entityIds = new Map(
    model.entities.map((entity, index) => [entity.name, `entity_${String(index + 1).padStart(4, "0")}`]),
  );
  const lines = [
    "digraph ConceptualModel {",
    `  graph ${dotAttributes([
      ["bgcolor", "transparent"],
      ["fontname", "Arial"],
      ["newrank", "true"],
      ["nodesep", "0.50"],
      ["outputorder", "edgesfirst"],
      ["overlap", "false"],
      ["pad", "0.20"],
      ["rankdir", "LR"],
      ["ranksep", "0.50"],
      ["splines", "spline"],
    ])};`,
    `  node ${dotAttributes([
      ["fontname", "Arial"],
      ["margin", "0"],
      ["shape", "plain"],
    ])};`,
    `  edge ${dotAttributes([
      ["color", theme.edge],
      ["fontcolor", theme.text],
      ["fontname", "Arial"],
      ["labelangle", "20"],
      ["labeldistance", "3.5"],
      ["labelfloat", "false"],
      ["minlen", "1"],
    ])};`,
    "",
  ];

  for (const entity of model.entities) {
    const label = entityHtmlLabel(entity, attributesByEntity.get(entity.name) || new Map(), theme);
    lines.push(`  ${entityIds.get(entity.name)} [class="entity-node", label=<${label}>];`);
  }

  const inheritanceLines = [];
  for (const entity of model.entities) {
    for (const parentName of entity.inherits_from) {
      inheritanceLines.push(
        `  ${entityIds.get(entity.name)} -> ${entityIds.get(parentName)} ${dotAttributes([
          ["arrowhead", "empty"],
          ["class", "inheritance-edge"],
          ["weight", "3"],
        ])};`,
      );
    }
  }
  if (inheritanceLines.length) lines.push("", ...inheritanceLines);

  if (model.relationships.length) lines.push("");
  for (const relationship of model.relationships) {
    const identifyingChild = identifyingChildren.get(relationship) || null;
    let tail = relationship.source;
    let head = relationship.target;
    if (identifyingChild && relationship.source.entity === identifyingChild) {
      tail = relationship.target;
      head = relationship.source;
    }
    /** @type {[string, string][]} */
    const attributes = [
      ["class", identifyingChild ? "relationship-edge identifying-relationship" : "relationship-edge"],
      ["dir", identifyingChild ? "both" : "none"],
      ["weight", identifyingChild ? "3" : "1"],
    ];
    if (identifyingChild) {
      attributes.push(["arrowhead", "none"], ["arrowtail", "diamond"]);
    }
    if (relationship.name) attributes.push(["label", relationship.name]);
    const tailLabel = relationshipEndLabel(tail);
    const headLabel = relationshipEndLabel(head);
    if (tailLabel) attributes.push(["taillabel", tailLabel]);
    if (headLabel) attributes.push(["headlabel", headLabel]);
    lines.push(
      `  ${entityIds.get(tail.entity)} -> ${entityIds.get(head.entity)} ${dotAttributes(attributes)};`,
    );
  }

  lines.push("}");
  return `${lines.join("\n")}\n`;
}
