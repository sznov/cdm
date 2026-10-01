import { checkpointPresentation } from "./checkpoint_presentation.js";

export function renderSequenceView(options = {}) {
  const elements = options.elements || {};
  const timeline = elements.sequenceTimeline;
  if (!timeline) return false;
  const traceEntries = options.traceEntries || [];
  const progressRows = options.progressRows || [];
  timeline.innerHTML = "";
  if (!traceEntries.length && !progressRows.length) {
    const empty = document.createElement("div");
    empty.className = "empty-trace";
    empty.textContent =
      options.traceLoadingRunId && options.traceLoadingRunId === options.selectedRunId
        ? "Loading checkpoints for the selected run..."
        : "No run checkpoints yet. Start a run to see the evaluated model checkpoints here.";
    timeline.append(empty);
    return true;
  }
  if (!progressRows.length) {
    const empty = document.createElement("div");
    empty.className = "empty-trace";
    empty.textContent = "Waiting for the first model checkpoint.";
    timeline.append(empty);
    return true;
  }

  const fragment = document.createDocumentFragment();
  progressRows.forEach((checkpoint) => {
    const entry = checkpoint.entry;
    const row = document.createElement("div");
    row.className = "sequence-row checkpoint-row";
    row.classList.toggle("is-running", checkpoint.running);
    row.classList.toggle("is-finalizing", checkpoint.finalizing);
    row.classList.toggle("is-complete", checkpoint.completed);
    row.classList.toggle("is-error", checkpoint.failed);
    row.classList.toggle("is-cancelled", checkpoint.cancelled);
    if (entry?.id === options.selectedTraceId) row.classList.add("selected");
    row.addEventListener("click", () => {
      if (!entry) return;
      options.onEntrySelected?.(entry);
    });

    const card = document.createElement("div");
    card.className = "sequence-card workflow-checkpoint-card";
    const head = document.createElement("div");
    head.className = "sequence-card-head";
    const presentation = checkpointPresentation(checkpoint);
    if (presentation.active) {
      const spinner = document.createElement("span");
      spinner.className = "phase-spinner checkpoint-spinner";
      spinner.setAttribute("aria-hidden", "true");
      head.append(spinner);
    }
    const title = document.createElement("strong");
    title.textContent = checkpoint.title;
    head.append(title);
    const status = document.createElement("span");
    status.className = `checkpoint-status checkpoint-status-${presentation.kind}`;
    status.textContent = presentation.label;
    head.append(status);
    const summary = document.createElement("p");
    summary.textContent = checkpoint.summary;
    card.append(head, summary);
    if (entry) options.appendCheckpointActions?.(card, checkpoint);
    row.append(card);
    fragment.append(row);
  });
  timeline.append(fragment);
  if (options.autoFollowTrace) timeline.scrollTop = 0;
  return true;
}
