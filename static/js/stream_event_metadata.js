export function agentIdForModelCallKind(kind) {
  const normalized = String(kind || "").toLowerCase();
  if (normalized.includes("modeling_plan")) return "modelingPlanner";
  if (normalized.includes("draft")) return "draftModeler";
  if (normalized.includes("structured_language")) return "structuredLanguageRepair";
  if (normalized.includes("plan_coverage")) return "planCoverageCritic";
  if (normalized.includes("patch_operation")) return "patchOperationClerk";
  if (normalized.includes("critic_patch_task")) return "criticPatchPlanner";
  if (normalized.includes("atomic_model_patch")) return "atomicModelPatcher";
  if (normalized.includes("semantic_patch")) return "semanticPatchValidator";
  if (normalized.includes("critic_model_patch")) return "criticModelPatcher";
  if (normalized.includes("gold") || normalized.includes("one_shot")) return "goldScaffoldModeler";
  if (normalized.includes("context")) return "contextAnalyst";
  if (normalized.includes("artifact") || normalized.includes("extraction")) return "artifactExtractor";
  if (normalized.includes("semantic") || normalized.includes("critic")) return "semanticCritic";
  if (normalized.includes("clerk")) return "operationClerk";
  if (normalized.includes("completion")) return "completionCheck";
  if (normalized.includes("language")) return "languageRepair";
  if (normalized.includes("planner") || normalized.includes("planning") || normalized.includes("change_request")) return "changePlanner";
  return "operationAgent";
}

export const STREAM_EVENT_LABELS = {
  obligation_extraction: "Obligation extraction",
  obligation_critic: "Obligation critic",
  obligation_model: "Obligation modeler",
  obligation_model_generation: "Obligation modeler",
  obligation_coverage: "Obligation coverage judge",
  association_concept_refinement: "Association concept refinement",
  relationship_local_refinement: "Relationship local refinement",
  relationship_local_critic: "Relationship local critic",
  coverage_repair: "Coverage repair",
  patch_operation_generation: "Patch operation clerk",
};

export function streamEventBase(event) {
  const suffix = ["_start", "_delta", "_done"].find((candidate) => event.endsWith(candidate));
  if (!suffix) return "";
  const base = event.slice(0, -suffix.length);
  return STREAM_EVENT_LABELS[base] ? base : "";
}
