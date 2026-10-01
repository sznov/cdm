import { terminalStatusFromPhaseText } from "./run_status.js";

export { terminalStatusFromPhaseText };

export function traceEventName(entry) {
  return String(entry?.event || "").toLowerCase();
}

export function phaseTitleFromStatus(text) {
  const value = String(text || "").toLowerCase();
  if (/error|fail/.test(value)) return "Failed";
  if (/^(stopped\b|cancelled\b|canceled\b|aborted\b)/.test(value) || /run cancelled by user/.test(value)) {
    return "Stopped";
  }
  if (/^(stopping\b|cancelling\b|canceling\b|aborting\b|stop requested\b)/.test(value)) {
    return "Stopping";
  }
  if (/start|prepar/.test(value)) return "Starting";
  if (/repair|rename|language/i.test(value)) return "Repairing";
  if (/draft|model/i.test(value)) return "Drafting";
  if (/patch|operation/i.test(value)) return "Patching";
  if (/correct/i.test(value)) return "Correcting";
  if (/ask|question/i.test(value)) return "Asking";
  if (/validat|check|critic|coverage/i.test(value)) return "Checking";
  if (/render|diagram|plantuml/i.test(value)) return "Rendering";
  return "Working";
}

export function phaseStatusFromTraceEntry(entry) {
  const event = traceEventName(entry);
  const payload = entry?.payload || {};
  if (event.includes("direct_baseline_generation")) {
    return `Generating direct baseline model attempt ${payload.batch_attempt || 1}...`;
  }
  if (event.includes("draft_model_generation")) {
    return `Generating draft model attempt ${payload.batch_attempt || 1}...`;
  }
  if (event.includes("structured_language_repair")) return "Checking structured model language...";
  if (event.includes("plan_coverage_critic")) return "Running plan coverage critic...";
  if (event.includes("critic_patch_task_planning")) return "Planning model revisions...";
  if (event.includes("atomic_model_patch")) return `Applying atomic patch ${payload.task_id || ""}...`.trim();
  if (event.includes("semantic_patch_validation")) return `Checking semantic patch ${payload.task_id || ""}...`.trim();
  if (event.includes("correction_patch_generation")) return "Generating correction patch operations...";
  if (event.includes("question_generation")) return "Generating answer...";
  if (event.includes("operation_generation")) {
    if (payload.iteration != null && payload.batch_attempt != null) {
      return `Iteration ${payload.iteration}, attempt ${payload.batch_attempt}: generating operation output...`;
    }
    return "Generating operation output...";
  }
  if (event.includes("modeling_plan_generation")) return "Generating modeling plan...";
  if (event.includes("one_shot_generation")) return "Generating complete structured model...";
  if (event.includes("plantuml") || event.includes("diagram")) return "Rendering diagram...";
  return "";
}

export function latestPhaseStatusFromTraceEntries(entries = []) {
  for (const entry of [...entries].reverse()) {
    const status = phaseStatusFromTraceEntry(entry);
    if (status) return status;
  }
  return "";
}

export function isModelCallTraceEvent(entry) {
  const event = String(entry?.event || "");
  if (event === "input_prompt") return true;
  if (event.endsWith("_generation_start") || event.endsWith("_generation_done")) return true;
  if (event.endsWith("_model_call_error")) return true;
  return [
    "structured_language_repair_start",
    "structured_language_repair_done",
    "plan_coverage_critic_start",
    "plan_coverage_critic_done",
  ].includes(event);
}

export function isTraceDeltaEvent(event) {
  return String(event || "").endsWith("_delta");
}

export function isTerminalTraceEntry(entry) {
  return ["done", "cancelled", "error"].includes(traceEventName(entry));
}

export function isNonCheckpointRetryEntry(entry) {
  return ["start", "done", "cancelled", "error", "correction_sequence_done", "correction_patch_chat_done"].includes(traceEventName(entry));
}
