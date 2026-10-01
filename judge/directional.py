from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.artifacts import write_json
from core.json_parsing import parse_json_object_output
from core.model_call_completion import complete_with_logging
from core.model_call_logger import ModelCallLogger
from core.model_client import CompletionResult, TextModelClient
from core.schemas import StructuredModel, validate_structured_model_links


RAW_ARTIFACT_KINDS = ("entities", "relationships", "attributes", "identifiers", "inheritances")
ARTIFACT_KINDS = ("entities", "relationships", "attributes", "identifiers")
DIRECTIONAL_COVERAGE_FIELD = "gold_represented"
DIRECTIONAL_SUPPORT_FIELD = "predicted_supported"


def load_structured_model(path: Path) -> StructuredModel:
    model = StructuredModel.model_validate(json.loads(path.read_text(encoding="utf-8")))
    validate_structured_model_links(model)
    return model


def round4(value: float) -> float:
    return round(float(value), 4)


def normalize_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 1.0
    if confidence > 1:
        confidence = confidence / 100.0
    return max(0.0, min(confidence, 1.0))


def directional_prf(
    *,
    represented_gold_count: int,
    supported_predicted_count: int,
    predicted_count: int,
    gold_count: int,
) -> dict[str, Any]:
    precision = supported_predicted_count / predicted_count if predicted_count else 0.0
    recall = represented_gold_count / gold_count if gold_count else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "gold_count": gold_count,
        "predicted_count": predicted_count,
        "represented_gold_count": represented_gold_count,
        "supported_predicted_count": supported_predicted_count,
        "precision": round4(precision),
        "recall": round4(recall),
        "f1": round4(f1),
    }


def relationship_end_payload(end: Any) -> dict[str, Any]:
    return {"entity": end.entity, "multiplicity": end.multiplicity, "role": end.role}


def relationship_endpoint_key(end: dict[str, Any]) -> tuple[str, str, str]:
    return (str(end.get("entity") or ""), str(end.get("role") or ""), str(end.get("multiplicity") or ""))


def order_neutral_relationship_endpoints(*ends: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(end) for end in sorted(ends, key=relationship_endpoint_key)]


def relationship_endpoint_label(end: dict[str, Any]) -> str:
    role = str(end.get("role") or "")
    multiplicity = str(end.get("multiplicity") or "")
    suffix_parts = [part for part in (role, multiplicity) if part]
    suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
    return f"{end.get('entity')}{suffix}"


def relationship_artifact_payload(
    *,
    artifact_id: str,
    name: str,
    source: dict[str, Any],
    target: dict[str, Any],
    structural_kind: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    endpoints = order_neutral_relationship_endpoints(source, target)
    payload: dict[str, Any] = {
        "id": artifact_id,
        "name": name,
        "source": source,
        "target": target,
        "endpoints": endpoints,
        "endpoint_order": "not_semantic",
        "label": label
        or f"{name or '<unnamed>'}: {relationship_endpoint_label(endpoints[0])} -- {relationship_endpoint_label(endpoints[1])}",
    }
    if structural_kind:
        payload["structural_kind"] = structural_kind
    return payload


def identifier_part_label(part: Any) -> str:
    return f"{part.kind}:{part.ref}"


def indexed_model_artifacts(model: StructuredModel, *, prefix: str) -> dict[str, list[dict[str, Any]]]:
    artifacts: dict[str, list[dict[str, Any]]] = {kind: [] for kind in RAW_ARTIFACT_KINDS}
    for index, entity in enumerate(model.entities, start=1):
        artifacts["entities"].append(
            {
                "id": f"{prefix}E{index}",
                "name": entity.name,
                "inherits_from": list(entity.inherits_from),
                "attributes": [attribute.name for attribute in entity.attributes],
                "identifier": [identifier_part_label(part) for part in entity.identifier],
            }
        )
        for attr_index, attribute in enumerate(entity.attributes, start=1):
            artifacts["attributes"].append(
                {
                    "id": f"{prefix}A{index}_{attr_index}",
                    "entity": entity.name,
                    "name": attribute.name,
                    "type": attribute.type,
                    "label": f"{entity.name}.{attribute.name}",
                }
            )
        if entity.identifier:
            artifacts["identifiers"].append(
                {
                    "id": f"{prefix}I{index}",
                    "entity": entity.name,
                    "parts": [identifier_part_label(part) for part in entity.identifier],
                    "label": f"{entity.name} identified by "
                    + ", ".join(identifier_part_label(part) for part in entity.identifier),
                }
            )
        for inheritance_index, parent in enumerate(entity.inherits_from, start=1):
            inheritance_id = f"{prefix}H{index}_{inheritance_index}"
            artifacts["inheritances"].append(
                {
                    "id": inheritance_id,
                    "child": entity.name,
                    "parent": parent,
                    "label": f"{entity.name} inherits from {parent}",
                }
            )
            artifacts["relationships"].append(
                relationship_artifact_payload(
                    artifact_id=inheritance_id,
                    name="inheritsFrom",
                    source={"entity": entity.name, "multiplicity": "1", "role": "subtype"},
                    target={"entity": parent, "multiplicity": "1", "role": "supertype"},
                    label=f"{entity.name} inherits from {parent}",
                    structural_kind="inheritance",
                )
            )
    for index, relationship in enumerate(model.relationships, start=1):
        artifacts["relationships"].append(
            relationship_artifact_payload(
                artifact_id=f"{prefix}R{index}",
                name=relationship.name or "",
                source=relationship_end_payload(relationship.source),
                target=relationship_end_payload(relationship.target),
            )
        )
    return artifacts


def evaluated_model_artifacts(artifacts: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return {kind: list(artifacts.get(kind, [])) for kind in ARTIFACT_KINDS}


def artifact_display_name(item: dict[str, Any]) -> str:
    return str(item.get("label") or item.get("name") or item.get("id") or "")


def normalize_id_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


def add_directional_entry(
    *,
    raw_entry: Any,
    expected_id_field: str,
    valid_ids: set[str],
    linked_id_field: str,
    confidence_threshold: float,
    accepted: dict[str, dict[str, Any]],
    invalid_entries: list[dict[str, Any]],
) -> None:
    if not isinstance(raw_entry, dict):
        invalid_entries.append({"entry": raw_entry, "reason": "entry is not an object"})
        return
    artifact_id = str(raw_entry.get(expected_id_field) or raw_entry.get("id") or "")
    confidence = normalize_confidence(raw_entry.get("confidence", 1.0))
    if confidence < confidence_threshold:
        invalid_entries.append({"entry": raw_entry, "reason": "confidence below threshold"})
        return
    if artifact_id not in valid_ids:
        invalid_entries.append({"entry": raw_entry, "reason": f"unknown {expected_id_field}"})
        return
    if artifact_id in accepted:
        invalid_entries.append({"entry": raw_entry, "reason": f"duplicate {expected_id_field}"})
        return
    accepted[artifact_id] = {
        "id": artifact_id,
        linked_id_field: normalize_id_list(raw_entry.get(linked_id_field)),
        "confidence": round4(confidence),
        "rationale": str(raw_entry.get("rationale") or raw_entry.get("reason") or "")[:500],
    }


def score_directional_artifact_kind(
    *,
    kind: str,
    gold_items: list[dict[str, Any]],
    predicted_items: list[dict[str, Any]],
    judge_result: dict[str, Any],
    confidence_threshold: float = 0.5,
) -> dict[str, Any]:
    gold_by_id = {str(item["id"]): item for item in gold_items}
    predicted_by_id = {str(item["id"]): item for item in predicted_items}
    represented: dict[str, dict[str, Any]] = {}
    supported: dict[str, dict[str, Any]] = {}
    invalid_entries: list[dict[str, Any]] = []

    accepted_kinds = {kind}
    if kind == "relationships":
        accepted_kinds.add("inheritances")

    for raw_entry in judge_result.get(DIRECTIONAL_COVERAGE_FIELD) or []:
        if isinstance(raw_entry, dict) and raw_entry.get("kind") not in (None, *accepted_kinds):
            continue
        add_directional_entry(
            raw_entry=raw_entry,
            expected_id_field="gold_id",
            valid_ids=set(gold_by_id),
            linked_id_field="predicted_ids",
            confidence_threshold=confidence_threshold,
            accepted=represented,
            invalid_entries=invalid_entries,
        )

    for raw_entry in judge_result.get(DIRECTIONAL_SUPPORT_FIELD) or []:
        if isinstance(raw_entry, dict) and raw_entry.get("kind") not in (None, *accepted_kinds):
            continue
        add_directional_entry(
            raw_entry=raw_entry,
            expected_id_field="predicted_id",
            valid_ids=set(predicted_by_id),
            linked_id_field="gold_ids",
            confidence_threshold=confidence_threshold,
            accepted=supported,
            invalid_entries=invalid_entries,
        )

    return {
        **directional_prf(
            represented_gold_count=len(represented),
            supported_predicted_count=len(supported),
            predicted_count=len(predicted_items),
            gold_count=len(gold_items),
        ),
        "kind": kind,
        "represented": [
            {**entry, "artifact": artifact_display_name(gold_by_id[artifact_id])}
            for artifact_id, entry in represented.items()
        ],
        "supported": [
            {**entry, "artifact": artifact_display_name(predicted_by_id[artifact_id])}
            for artifact_id, entry in supported.items()
        ],
        "missing": [artifact_display_name(item) for item in gold_items if str(item["id"]) not in represented],
        "unsupported": [artifact_display_name(item) for item in predicted_items if str(item["id"]) not in supported],
        "invalid_entries": invalid_entries,
    }


def aggregate_directional_scores(scores_by_kind: dict[str, dict[str, Any]]) -> dict[str, Any]:
    total_gold = sum(int(score["gold_count"]) for score in scores_by_kind.values())
    total_predicted = sum(int(score["predicted_count"]) for score in scores_by_kind.values())
    total_represented_gold = sum(int(score["represented_gold_count"]) for score in scores_by_kind.values())
    total_supported_predicted = sum(int(score["supported_predicted_count"]) for score in scores_by_kind.values())
    active_scores = [score for score in scores_by_kind.values() if int(score["gold_count"]) or int(score["predicted_count"])]
    macro_f1 = sum(float(score["f1"]) for score in active_scores) / max(len(active_scores), 1)
    return {
        **directional_prf(
            represented_gold_count=total_represented_gold,
            supported_predicted_count=total_supported_predicted,
            predicted_count=total_predicted,
            gold_count=total_gold,
        ),
        "macro_f1": round4(macro_f1),
    }


def score_directional_all_artifacts(
    *,
    gold_artifacts: dict[str, list[dict[str, Any]]],
    predicted_artifacts: dict[str, list[dict[str, Any]]],
    judge_result: dict[str, Any],
    confidence_threshold: float = 0.5,
) -> dict[str, Any]:
    scores = {
        kind: score_directional_artifact_kind(
            kind=kind,
            gold_items=gold_artifacts[kind],
            predicted_items=predicted_artifacts[kind],
            judge_result=judge_result,
            confidence_threshold=confidence_threshold,
        )
        for kind in ARTIFACT_KINDS
    }
    return {"aggregate": aggregate_directional_scores(scores), "by_kind": scores}


DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE = "historical_v1"


SHORT_DIRECTIONAL_JUDGE_SYSTEM_PROMPT = (
    "You are a strict coverage/support semantic evaluator for conceptual ER models. "
    "Return JSON only. The gold model is a reference possible model, not the only correct solution. "
    "Use the specification as the authority. Judge whether each artifact's concept or fact is adequately "
    "represented anywhere in the opposite model. Do not require exact names or one-to-one artifact shape matches."
)

SHORT_DIRECTIONAL_JUDGE_USER_TEMPLATE = (
    "Evaluate the predicted ER model against the gold/reference model for recall and precision.\n\n"
    "Recall: add one entry to gold_represented for every gold artifact whose concept or fact is "
    "represented adequately somewhere in the predicted model.\n"
    "Precision: add one entry to predicted_supported for every predicted artifact whose concept or fact "
    "is supported by the specification and compatible with the reference model's conceptual scope.\n\n"
    "Rules:\n"
    "- Use artifact IDs exactly as provided.\n"
    "- Include kind on every entry: entities, relationships, attributes, or identifiers.\n"
    "- Inheritance/subtype artifacts are relationship artifacts for evaluation.\n"
    "- Alternate representations are valid when they preserve the same required facts and constraints.\n"
    "- Do not mark artifacts represented/supported merely because names are similar.\n"
    "- Omit unsupported/unrepresented artifacts from positive lists; use notes for important ambiguity.\n\n"
    "Return exactly one JSON object with this shape:\n"
    "{\n"
    '  "gold_represented": [{"kind": "relationships", "gold_id": "GR1", "predicted_ids": ["PR1"]}],\n'
    '  "predicted_supported": [{"kind": "relationships", "predicted_id": "PR1", "gold_ids": ["GR1"]}],\n'
    '  "notes": "short evaluator note"\n'
    "}\n\n"
    "Specification:\n{{SPECIFICATION}}\n\n"
    "Artifacts:\n{{ARTIFACTS}}"
)

HISTORICAL_DIRECTIONAL_JUDGE_SYSTEM_PROMPT = (
    "You are a strict coverage/support semantic evaluator for conceptual ER models. Return JSON only. "
    "The gold model is a reference possible model, not the only correct solution and not an exact canonical target. "
    "Use the specification as the authority. If the gold and predicted models differ but both are defensible, "
    "semantically coherent interpretations of the specification, credit the artifact as represented/supported and "
    "mention the ambiguity briefly in notes if useful. "
    "Do not require one-to-one artifact shape matches. Judge whether each artifact's concept or fact is "
    "adequately represented anywhere in the opposite model. Alternate representations can be valid: "
    "a plain many-to-many relationship may be represented by a reified association entity with two participant "
    "relationships, and a small lookup entity may represent a scalar fact when that is a faithful modeling choice. "
    "Do not require a separate entity unless the specification implies independent identity, lifecycle, history, "
    "repeated occurrences, temporal/result/status facts, own attributes, own relationships, or participation in "
    "stored constraints; otherwise a scalar, flag, type attribute, or lookup representation may be adequate. "
    "For precision, a plausible operational refinement is not automatically supported. Credit extra predicted "
    "temporal, ordering, audit, file, code, limit, threshold, status, or validation facts only when the specification "
    "states or implies that the fact is stored, such as through history, tracking, evidence, generated file, status "
    "lifecycle, ordered list/document item, required count, code, limit, or threshold wording. If the fact is merely "
    "useful real-world design, omit it from predicted_supported and mention it as plausible unsupported if important. "
    "Treat a fact as represented when it is deterministically and losslessly derivable from modeled facts and "
    "relationships. Also credit a more compact representation when it is a normal, defensible modeling shortcut "
    "for the specification and does not lose required distinctions. Do not credit arbitrary guesses from labels, "
    "optional paths, or unstated rules. "
    "Accept classification represented by a lookup entity, scalar type/status attribute, subtype structure, "
    "controlled/named category values, or another queryable classification construct when it preserves the same "
    "distinctions required by the specification. Do not require a separate type lookup when a package/category/name "
    "structure is a defensible way to carry the distinction and the specification does not require an independent "
    "type lifecycle. If a scalar/type/status field is extracted into a lookup entity, the lookup must preserve all "
    "meaningful semantics carried by the original values, including codes, required counts, limits, thresholds, "
    "or rules tied to the category. A name-only lookup that loses those facts is only partial coverage/support. "
    "Accept stored aggregate facts as represented when the atomic facts and mandatory derivation path are modeled "
    "unambiguously. Do not require invented domain-specific key attributes unless the specification states or "
    "strongly implies them; surrogate identifiers are acceptable when a complete stable contextual/natural identity "
    "is not stated or strongly implied. When the specification does not disambiguate identity, credit any stable "
    "identifier that reasonably distinguishes instances without contradicting the domain. "
    "If a meaningful supertype remains modeled, shared names, identifiers, and common properties should remain on "
    "the supertype unless the specification gives subtype-specific semantics. Do not treat pushing the same common "
    "fact down into multiple subtypes as an improvement when it duplicates or removes the shared supertype fact. "
    "When a fact belongs to a process, registration, order, enrollment, session, document, event, or similar "
    "contextual entity, prefer the contextual attachment; a direct link to a participant/object is adequate only "
    "when it does not lose needed context for multiple occurrences. If the specification does not require the "
    "contextual distinction and a participant/object-level representation is common and coherent, credit it. "
    "When a fact is stated in the context of a membership, role, appointment, assignment, registration, or process, "
    "a direct person/object attribute or relationship is adequate only if the role/process context is still recoverable "
    "or irrelevant to the specification. "
    "If an institution, employer, or affiliation fact is stated for a member, role holder, appointee, "
    "assignment, or other contextual participation, require the role/membership/assignment context; "
    "a direct person/object-to-institution relationship alone is not enough unless that context remains "
    "recoverable or irrelevant. "
    "For prerequisites, qualifications, eligibility evidence, certificates, approvals, exams, checks, or similar "
    "facts that qualify a participant for a process, credit participant-level representation when the specification "
    "does not require recording the exact process instance that consumed the evidence. A participant-level fact may "
    "represent a process-level reference if validity, category, date, status, or result facts are sufficient for the "
    "stated information needs, or if the specification only requires knowing that the participant satisfies the "
    "prerequisite. Do not require reifying such facts as events when the specification only requires a scalar state "
    "or eligibility condition. "
    "Credit semantically equivalent relationship paths, not only direct edges, when the path preserves the same "
    "required fact and does not lose a distinction required by the specification. If the reference model links A "
    "directly to C, and the predicted model represents the same fact through A -> B -> C, count it as represented "
    "when B is the natural owner, participant, or context for C and the specification does not require storing the "
    "direct A-C association separately. "
    "Do not require administrative/user/access-control actors unless the specification says their assignments, "
    "actions, approvals, ownership, audit trail, or other persisted facts are stored. "
    "Status may be represented by a lookup, scalar state, boolean flag, event/date, or derived condition if it "
    "supports the required distinctions and lifecycle. Do not mark a predicted status/history/change-event "
    "entity unsupported solely because the reference stores only the current status. If the specification "
    "requires tracking, changing, monitoring, lifecycle progression, auditability, or history of a "
    "state/status, a reified status-change/history entity linked to the subject and status is a valid "
    "refinement, especially when it stores date/time, actor, reason, or transition facts. Phrases requiring "
    "tracking and changing a status are sufficient support for such a refinement; do not require an explicit "
    "audit-log or history-table phrase. Penalize it only "
    "when it contradicts the current-state model, prevents determining the current status, duplicates current "
    "status with no derivation/synchronization path, or invents history where the specification only requires "
    "a simple current value. "
    "For relationship artifacts that encode inheritance/subtype distinctions, judge the subtype distinction conceptually: an inheritance can be "
    "covered by explicit subclassing, a type/discriminator lookup, a role/category entity, or another coherent "
    "structure if it preserves the same stored facts, constraints, and query capability. If the hierarchy has "
    "no subclass-specific attributes or relationships and only records a category/type distinction, a faithful "
    "type lookup or discriminator can fully represent it. Do not require the opposite model to use an "
    "inheritance edge when an alternate representation is semantically adequate. "
    "Reject unsupported UI/report/procedure artifacts, unsupported lookup extraction, wrong participant semantics, "
    "wrong identity rules, and multiplicities that contradict the specification or materially change required "
    "domain semantics. For relationship artifacts, multiplicity belongs to the "
    "endpoint entity/role, not to the written source/target or first/second endpoint order. Endpoint order "
    "is not semantic; a relationship with endpoints listed in the opposite order is equivalent only when "
    "the same endpoint entities keep the same endpoint multiplicities and roles."
)

HISTORICAL_DIRECTIONAL_JUDGE_USER_TEMPLATE = (
    "Evaluate the predicted ER model against the gold model for recall and precision.\n\n"
    "Recall accounting: add one entry to gold_represented for every gold artifact whose concept/fact is "
    "represented adequately somewhere in the predicted model. Treat each gold artifact as a probe for a concept, "
    "not as a required exact structure. Use predicted_ids to cite the artifact or artifacts that represent it.\n"
    "Precision accounting: add one entry to predicted_supported for every predicted artifact whose concept/fact is "
    "supported by the specification and is compatible with the reference model's conceptual scope. Use gold_ids "
    "to cite the artifact or artifacts that support it; if support comes mostly from the specification rather than "
    "one exact gold artifact, cite the closest relevant gold artifact(s) and explain briefly.\n\n"
    "Keep the JSON compact. Omit confidence and rationale fields for ordinary accepted entries; the scorer will "
    "default confidence to 1.0. Use notes for only the most important ambiguities or unsupported artifacts.\n\n"
    "Important accounting rules:\n"
    "- Use artifact ids exactly as provided.\n"
    "- Include kind on every entry: entities, relationships, attributes, or identifiers. Inheritance/subtype artifacts are relationship artifacts for evaluation.\n"
    "- The reference model is one valid solution. If predicted and reference choices are both plausible from the specification and neither loses required facts or constraints, count them as hits.\n"
    "- A generated association entity and its two participant relationships may all be supported by one gold M:N relationship if it is a faithful alternate representation.\n"
    "- For entity artifacts, credit alternate scalar/flag/type/status/lookup representations only when the specification does not require separate lifecycle, history, repeated instances, own attributes, own relationships, or stored constraints for that concept.\n"
    "- For precision, credit extra predicted temporal, ordering, audit, file, code, limit, threshold, status, or validation facts only when the specification states or implies that the fact is stored. Useful real-world additions are not errors, but omit them from predicted_supported when they are not spec-grounded.\n"
    "- For attributes and relationships, credit deterministic lossless derivations through mandatory modeled paths. Also credit compact/common-sense representations when the specification does not require the expanded reference structure. Do not credit arbitrary label guesses, optional paths that may be absent, or assumptions that contradict the specification.\n"
    "- For identifier artifacts, credit contextual/natural identifiers when they are complete, stable, and spec-derived; also credit surrogate or alternative stable identifiers when the specification does not clearly require the reference identifier.\n"
    "- For classification artifacts, accept lookup entities, scalar type/status attributes, subtype structures, controlled/named category values, or other queryable classifications when they preserve the distinctions required by the specification. If a lookup replaces a scalar/type/status value, it must preserve any code, count, limit, threshold, or rule semantics carried by that value.\n"
    "- For aggregate artifacts, accept derivation from modeled atomic facts when the derivation path is complete, mandatory, and unambiguous.\n"
    "- If a meaningful supertype remains modeled, shared names, identifiers, and common properties should stay on the supertype. Do not credit subtype-only duplication as equivalent when it loses the shared supertype fact.\n"
    "- For administrative/user/access-control artifacts, require persisted assignments, actions, approvals, ownership, audit trail, or similar stored facts before counting them as mandatory conceptual artifacts.\n"
    "- Do not mark a predicted status/history/change-event entity unsupported solely because the reference stores only the current status. If the specification requires tracking, changing, monitoring, lifecycle progression, auditability, or history of a state/status, a reified status-change/history entity linked to the subject and status is a valid refinement, especially when it stores date/time, actor, reason, or transition facts. Penalize it only when it contradicts the current-state model, prevents determining the current status, duplicates current status with no derivation/synchronization path, or invents history where the specification only requires a simple current value.\n"
    "- Phrases requiring tracking and changing a status are sufficient support for a status-change/history entity; do not require the specification to literally say audit log or history table.\n"
    "- For process-context facts, prefer attachment to the contextual entity, but credit direct participant/object links when the specification does not require the extra context or when both interpretations are defensible.\n"
    "- For membership, role, appointment, assignment, registration, or process-context facts, require the context when the specification uses that context semantically. Direct participant/object facts are hits only when the context is recoverable or irrelevant.\n"
    "- For institution, employer, or affiliation facts stated for a member, role holder, appointee, assignment, or contextual participation, require that context. A direct person/object-to-institution relationship alone is not enough unless the context is recoverable or irrelevant.\n"
    "- For prerequisite/qualification/evidence facts, credit participant-level links, participant-level attributes, or participant-plus-classification facts when they can answer the same eligibility or status question and the specification does not require tracking exactly which process instance used the evidence.\n"
    "- Do not require a separate event/exam/certificate entity for a prerequisite when the specification only requires a yes/no, current-validity, or eligibility state; require reification only when attempts, dates, results, renewals, history, documents, or participant relationships must be stored independently.\n"
    "- Credit semantically equivalent relationship paths, not only direct edges, when the path preserves the same required fact and does not lose a distinction required by the specification.\n"
    "- If the reference model links A directly to C, and the predicted model represents the same fact through A -> B -> C, count it as represented when B is the natural owner/participant/context for C and the specification does not require storing the direct A-C association separately.\n"
    "- For relationship entries that represent inheritance/subtype distinctions, mark them represented/supported if the opposite model still distinguishes the subtype and supports equivalent subtype-specific facts or constraints. If there are no subclass-specific facts, a faithful discriminator/type lookup/role entity is enough. Cite all opposite-model artifacts that provide that representation.\n"
    "- For relationships, source/target or first/second endpoint order is irrelevant; compare multiplicities by matched endpoint entity and role. Gold A(1)--B(0..*) and predicted B(0..*)--A(1) may match; gold A(1)--B(0..*) and predicted A(0..*)--B(1) must not be credited as the same relationship because the endpoint multiplicities changed.\n"
    "- Relationship artifacts include an endpoints list for order-neutral participant comparison; source and target preserve original IR storage order only.\n"
    "- Do not reject a relationship solely because optionality or cardinality differs from the reference. Reject it only when the specification disambiguates the multiplicity or the difference materially changes a required domain rule. If both multiplicities are defensible, count it as a hit.\n"
    "- If an artifact is only partially represented and loses important required context, lifecycle, identity, multiplicity, or constraints, omit it from the positive lists and explain briefly in notes.\n"
    "- Do not mark an artifact represented/supported just because names are similar.\n"
    "- Omit unsupported/unrepresented artifacts from the positive lists; optionally cite them in notes only.\n"
    "- Keep rationales terse or empty.\n\n"
    "Return exactly one JSON object with this shape:\n"
    "{\n"
    '  "gold_represented": [{"kind": "relationships", "gold_id": "GR1", "predicted_ids": ["PR1"]}],\n'
    '  "predicted_supported": [{"kind": "relationships", "predicted_id": "PR1", "gold_ids": ["GR1"]}],\n'
    '  "notes": "short evaluator note"\n'
    "}\n\n"
    "Specification:\n{{SPECIFICATION}}\n\n"
    "Artifacts:\n{{ARTIFACTS}}"
)


@dataclass(frozen=True, slots=True)
class DirectionalJudgePromptProfile:
    id: str
    system_prompt: str
    user_template: str


DIRECTIONAL_JUDGE_PROMPT_PROFILES: dict[str, DirectionalJudgePromptProfile] = {
    "historical_v1": DirectionalJudgePromptProfile(
        id="historical_v1",
        system_prompt=HISTORICAL_DIRECTIONAL_JUDGE_SYSTEM_PROMPT,
        user_template=HISTORICAL_DIRECTIONAL_JUDGE_USER_TEMPLATE,
    ),
    "short_v1": DirectionalJudgePromptProfile(
        id="short_v1",
        system_prompt=SHORT_DIRECTIONAL_JUDGE_SYSTEM_PROMPT,
        user_template=SHORT_DIRECTIONAL_JUDGE_USER_TEMPLATE,
    ),
}
DIRECTIONAL_JUDGE_PROMPT_PROFILE_IDS = tuple(DIRECTIONAL_JUDGE_PROMPT_PROFILES)


def directional_judge_prompt_profile(prompt_profile_id: str | None = None) -> DirectionalJudgePromptProfile:
    profile_id = prompt_profile_id or DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE
    try:
        return DIRECTIONAL_JUDGE_PROMPT_PROFILES[profile_id]
    except KeyError as exc:
        valid = ", ".join(DIRECTIONAL_JUDGE_PROMPT_PROFILE_IDS)
        raise ValueError(f"Unknown directional judge prompt profile {profile_id!r}. Valid profiles: {valid}") from exc


def render_directional_judge_user_content(
    *,
    profile: DirectionalJudgePromptProfile,
    specification: str,
    payload: str,
) -> str:
    return profile.user_template.replace("{{SPECIFICATION}}", specification).replace("{{ARTIFACTS}}", payload)


def build_directional_model_judge_messages(
    *,
    specification: str,
    gold_artifacts: dict[str, list[dict[str, Any]]],
    predicted_artifacts: dict[str, list[dict[str, Any]]],
    prompt_profile_id: str | None = DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE,
) -> list[dict[str, str]]:
    gold_eval_artifacts = evaluated_model_artifacts(gold_artifacts)
    predicted_eval_artifacts = evaluated_model_artifacts(predicted_artifacts)
    payload = json.dumps(
        {"gold_artifacts": gold_eval_artifacts, "predicted_artifacts": predicted_eval_artifacts},
        ensure_ascii=False,
        indent=2,
    )
    profile = directional_judge_prompt_profile(prompt_profile_id)
    return [
        {"role": "system", "content": profile.system_prompt},
        {"role": "user", "content": render_directional_judge_user_content(profile=profile, specification=specification, payload=payload)},
    ]


def parse_directional_model_judge_output(raw_output: str) -> dict[str, Any]:
    payload = parse_json_object_output(raw_output, label="Directional model judge")
    return {
        DIRECTIONAL_COVERAGE_FIELD: payload.get(DIRECTIONAL_COVERAGE_FIELD)
        if isinstance(payload.get(DIRECTIONAL_COVERAGE_FIELD), list)
        else [],
        DIRECTIONAL_SUPPORT_FIELD: payload.get(DIRECTIONAL_SUPPORT_FIELD)
        if isinstance(payload.get(DIRECTIONAL_SUPPORT_FIELD), list)
        else [],
        "notes": str(payload.get("notes") or "")[:2000],
        "raw": payload,
    }


class DirectionalModelJudgeClient:
    def __init__(
        self,
        client: TextModelClient,
        *,
        logger: ModelCallLogger | None = None,
        prompt_profile_id: str | None = DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE,
    ) -> None:
        self.client = client
        self.logger = logger
        self.prompt_profile_id = directional_judge_prompt_profile(prompt_profile_id).id

    async def judge(
        self,
        *,
        specification: str,
        gold_artifacts: dict[str, list[dict[str, Any]]],
        predicted_artifacts: dict[str, list[dict[str, Any]]],
        output_dir: Path | None = None,
    ) -> tuple[dict[str, Any], CompletionResult]:
        messages = build_directional_model_judge_messages(
            specification=specification,
            gold_artifacts=gold_artifacts,
            predicted_artifacts=predicted_artifacts,
            prompt_profile_id=self.prompt_profile_id,
        )
        system_prompt = messages[0]["content"]
        user_content = messages[1]["content"]
        if output_dir is not None:
            write_json(
                output_dir / "directional_judge_prompt.json",
                {
                    "prompt_profile_id": self.prompt_profile_id,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                },
            )
        if self.logger is None:
            completion = await self.client.complete(system_prompt=system_prompt, user_content=user_content, messages=messages)
            log_record = None
        else:
            completion, log_record = await complete_with_logging(
                client=self.client,
                logger=self.logger,
                kind="directional_semantic_judge",
                system_prompt=system_prompt,
                user_content=user_content,
                messages=messages,
            )
        if output_dir is not None:
            write_json(
                output_dir / "directional_judge_output.json",
                {
                    "content": completion.text,
                    "model": completion.model,
                    "usage": completion.usage,
                    "raw_response": completion.raw_response,
                    "model_call_log": log_record,
                },
            )
        parsed = parse_directional_model_judge_output(completion.text)
        parsed["usage"] = completion.usage
        parsed["prompt_profile_id"] = self.prompt_profile_id
        return parsed, completion


async def evaluate_structured_model_pair_directional(
    *,
    gold_model: StructuredModel,
    predicted_model: StructuredModel,
    specification: str,
    judge_client: DirectionalModelJudgeClient,
    output_dir: Path | None = None,
    confidence_threshold: float = 0.5,
) -> dict[str, Any]:
    raw_gold_artifacts = indexed_model_artifacts(gold_model, prefix="G")
    raw_predicted_artifacts = indexed_model_artifacts(predicted_model, prefix="P")
    gold_artifacts = evaluated_model_artifacts(raw_gold_artifacts)
    predicted_artifacts = evaluated_model_artifacts(raw_predicted_artifacts)
    judge_result, completion = await judge_client.judge(
        specification=specification,
        gold_artifacts=gold_artifacts,
        predicted_artifacts=predicted_artifacts,
        output_dir=output_dir,
    )
    score = score_directional_all_artifacts(
        gold_artifacts=gold_artifacts,
        predicted_artifacts=predicted_artifacts,
        judge_result=judge_result,
        confidence_threshold=confidence_threshold,
    )
    result = {
        "artifact_counts": {
            "gold": {kind: len(gold_artifacts[kind]) for kind in ARTIFACT_KINDS},
            "predicted": {kind: len(predicted_artifacts[kind]) for kind in ARTIFACT_KINDS},
            "raw_gold": {kind: len(raw_gold_artifacts[kind]) for kind in RAW_ARTIFACT_KINDS},
            "raw_predicted": {kind: len(raw_predicted_artifacts[kind]) for kind in RAW_ARTIFACT_KINDS},
        },
        "directional_semantic_score": score,
        "directional_semantic_judge": judge_result,
        "judge_prompt_profile": judge_client.prompt_profile_id,
        "judge_model": completion.model,
        "judge_usage": completion.usage,
    }
    if output_dir is not None:
        write_json(output_dir / "evaluation.json", result)
    return result


async def evaluate_model_files_directional(
    *,
    gold_model_path: Path,
    predicted_model_path: Path,
    specification_path: Path | None,
    output_dir: Path,
    judge_client: DirectionalModelJudgeClient,
    confidence_threshold: float = 0.5,
) -> dict[str, Any]:
    specification = specification_path.read_text(encoding="utf-8") if specification_path and specification_path.exists() else ""
    result = await evaluate_structured_model_pair_directional(
        gold_model=load_structured_model(gold_model_path),
        predicted_model=load_structured_model(predicted_model_path),
        specification=specification,
        judge_client=judge_client,
        output_dir=output_dir,
        confidence_threshold=confidence_threshold,
    )
    result.update(
        {
            "gold_model_path": str(gold_model_path),
            "predicted_model_path": str(predicted_model_path),
            "specification_path": str(specification_path) if specification_path else None,
        }
    )
    write_json(output_dir / "evaluation.json", result)
    return result


__all__ = [
    "ARTIFACT_KINDS",
    "DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE",
    "DIRECTIONAL_JUDGE_PROMPT_PROFILE_IDS",
    "DIRECTIONAL_JUDGE_PROMPT_PROFILES",
    "DIRECTIONAL_COVERAGE_FIELD",
    "DIRECTIONAL_SUPPORT_FIELD",
    "DirectionalJudgePromptProfile",
    "DirectionalModelJudgeClient",
    "build_directional_model_judge_messages",
    "directional_judge_prompt_profile",
    "evaluate_model_files_directional",
    "evaluate_structured_model_pair_directional",
    "evaluated_model_artifacts",
    "indexed_model_artifacts",
    "parse_directional_model_judge_output",
    "score_directional_all_artifacts",
]
