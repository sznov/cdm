import {
  cleanDecisionPatchText,
} from "./decision_patch_text.js";
import { appendDecisionPatchChoiceControls } from "./decision_card_options.js";

export { renderDecisionSupersededNote } from "./decision_card_superseded.js";

export function createDecisionPatchCard(patch, options = {}) {
  const allowControls = Boolean(options.allowControls);
  const readOnly = Boolean(options.readOnly);
  const transcript = Boolean(options.transcript);
  const status = String(patch.status || "pending");
  const hasOperation = Boolean(patch.operation);
  const actionable = allowControls && hasOperation && !["applied", "rejected", "noted"].includes(status);
  const row = document.createElement("article");
  row.className = `decision-patch ${status} ${transcript ? "transcript-card transcript-decision-card" : ""} ${
    actionable ? "actionable has-options" : hasOperation ? "actionable" : "informational"
  }`;
  if (patch.id) row.dataset.patchId = patch.id;

  const body = document.createElement("div");
  body.className = "decision-patch-body";
  const titleText = cleanDecisionPatchText(patch.title || patch.question || patch.reason || patch.id || "Decision patch");
  const questionText = cleanDecisionPatchText(patch.question || "");
  const reasonText = cleanDecisionPatchText(patch.reason || "");
  const evidenceText = cleanDecisionPatchText(patch.evidence || "");

  const title = document.createElement("div");
  title.className = "decision-patch-title";
  const titleLabel = document.createElement("span");
  titleLabel.textContent = titleText;
  title.append(titleLabel);
  body.append(title);

  if (questionText && questionText !== titleText) {
    const question = document.createElement("p");
    question.className = "decision-patch-question";
    question.textContent = questionText;
    body.append(question);
  }
  if (reasonText && reasonText !== titleText && reasonText !== questionText) {
    const reason = document.createElement("p");
    reason.className = "decision-patch-reason";
    reason.textContent = reasonText;
    body.append(reason);
  }
  if (evidenceText) {
    const evidence = document.createElement("p");
    evidence.className = "decision-patch-evidence";
    evidence.textContent = evidenceText;
    body.append(evidence);
  }

  appendDecisionPatchChoiceControls(row, body, patch, titleText, {
    ...options,
    actionable,
    readOnly,
  });

  row.append(body);
  return row;
}
