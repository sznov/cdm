import { titleFromIdentifier } from "./format.js";

export const RUNTIME_AGENT_NAMES = {
  artifactExtractor: "Artifact Extractor",
  asyncPlantumlRenderer: "PlantUML Renderer",
  changePlanner: "Change Planner",
  completionCheck: "Completion Check",
  correctionSequence: "Correction Sequence",
  directBaseline: "Direct Baseline",
  draftModeler: "Draft Modeler",
  goldScaffoldModeler: "Draft Modeler",
  incrementalOpApplier: "Patch Applier",
  languageRepair: "Language Repair",
  modelQuestionAnswerer: "Model Question Answerer",
  operationAgent: "Patch Clerk",
  operationClerk: "Patch Clerk",
  patchOperationClerk: "Patch Clerk",
  planCoverageCritic: "Review Critic",
  renderer: "PlantUML Renderer",
  runtime: "Runtime",
  spec: "Specification",
  structuredLanguageRepair: "Language Repair",
  structuredValidator: "Structured Validator",
  toolSplitter: "Tool Splitter",
  validator: "Structured Validator",
};

export function runtimeAgentById(runtimeHarness, id) {
  const agentId = String(id || "").trim();
  if (!agentId) return null;
  const node = runtimeHarness?.nodes?.find?.((candidate) => candidate.id === agentId);
  return {
    id: agentId,
    name: node?.name || RUNTIME_AGENT_NAMES[agentId] || titleFromIdentifier(agentId),
  };
}

export function selectedAgentForEvent(runtimeHarness, event, payload = {}) {
  const agentById = (id) => runtimeAgentById(runtimeHarness, id);
  if (payload.agent_id) return agentById(payload.agent_id);
  if (event === "artifact_extraction") return agentById("artifactExtractor");
  if (event === "context_analysis") return agentById("contextAnalyst");
  if (event === "change_requests_planned") return agentById("changePlanner");
  if (event === "tool_calls_split") return agentById("toolSplitter");
  if (event.startsWith("direct_baseline_")) return agentById("directBaseline");
  if (event.startsWith("one_shot_generation")) return agentById("goldScaffoldModeler");
  if (event === "model_generation_interrupted") return agentById(payload.agent_id) || agentById("operationAgent") || agentById("goldScaffoldModeler");
  if (event === "input_prompt" || event.startsWith("operation_generation") || event === "operation_batch_raw") {
    return agentById("operationAgent") || agentById("operationClerk");
  }
  if (event === "structured_model_validated") return agentById("validator");
  if (event === "partial_model_snapshot") return agentById("asyncPlantumlRenderer") || agentById("renderer");
  if (event === "structured_patch_operation_candidate") return agentById("patchOperationClerk");
  if (event === "structured_patch_operation_applied") return agentById("incrementalOpApplier");
  if (event === "structured_patch_operation_parse_error") return agentById("patchOperationClerk");
  if (event === "operation_batch_applied") return agentById("validator");
  if (event === "odd_one_out_evaluation") return agentById("validator");
  if (event === "odd_one_out_oracle_evaluation") return agentById("oracleEvaluator");
  if (event === "odd_one_out_retry_feedback") return agentById("validator");
  if (event === "language_name_repair") return agentById("languageRepair");
  if (event === "semantic_operation_critic") return agentById("semanticCritic");
  if (event === "completion_check") return agentById("completionCheck");
  if (event === "plantuml_preview" || event === "done") return agentById("renderer");
  return null;
}
