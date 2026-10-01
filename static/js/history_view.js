export function appendHistoryView(elements, payload = {}) {
  if (!elements.history) return;
  const item = document.createElement("div");
  item.className = "history-item";
  const accepted = payload.accepted?.length ?? 0;
  const rejected = payload.rejected?.length ?? 0;
  if (rejected) item.classList.add("has-errors");

  const title = document.createElement("strong");
  title.append(`Iteration ${payload.iteration}, attempt ${payload.batch_attempt}: accepted ${accepted}, `);
  const rejectedLabel = document.createElement("span");
  rejectedLabel.className = rejected ? "bad" : "";
  rejectedLabel.textContent = `rejected ${rejected}`;
  title.append(rejectedLabel);
  item.append(title);

  const focus = document.createElement("div");
  focus.textContent = payload.focus || "";
  item.append(focus);

  if (payload.language_repair?.changed) {
    const repair = document.createElement("div");
    repair.className = "repair-note";
    const changes = (payload.language_repair.changes || [])
      .map((change) => `${change.from} -> ${change.to}`)
      .join(", ");
    repair.textContent = `Language name repair: ${changes}`;
    item.append(repair);
  }

  if (payload.completion_check) {
    const check = document.createElement("div");
    check.className = "repair-note";
    const outcome = payload.completion_check.complete ? "complete" : "incomplete";
    const nextFocus = payload.completion_check.next_focus ? `; next: ${payload.completion_check.next_focus}` : "";
    check.textContent = `Completion check: ${outcome}${nextFocus}`;
    item.append(check);
  }

  if (payload.semantic_critic?.length) {
    const critic = document.createElement("div");
    critic.className = "repair-note";
    const rejectedReviews = payload.semantic_critic.filter((review) => review.accepted === false);
    critic.textContent = rejectedReviews.length
      ? `Semantic critic rejected: ${rejectedReviews.map((review) => review.feedback || review.reason || "unsupported operation").join("; ")}`
      : `Semantic critic accepted ${payload.semantic_critic.length} operation(s).`;
    item.append(critic);
  }

  if (rejected) {
    const errors = document.createElement("ul");
    errors.className = "validation-errors";
    for (const rejection of payload.rejected || []) {
      const error = document.createElement("li");
      const index = rejection.index ?? "?";
      error.textContent = `Operation ${index}: ${rejection.error || "Validation failed."}`;
      errors.append(error);
    }
    item.append(errors);
  }

  elements.history.prepend(item);
}
