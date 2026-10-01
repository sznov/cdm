import { els } from "./dom.js";
import {
  formatLocalTime,
  shortRunId,
} from "./format.js";

export function renderRunListView(options = {}) {
  const {
    onCancelRun,
    onLoadRun,
    runRecords = [],
    selectedRunId,
  } = options;
  if (!els.runList) return;
  els.runList.innerHTML = "";
  if (!runRecords.length) {
    const empty = document.createElement("div");
    empty.className = "empty-trace";
    empty.textContent = "No persisted runs yet. Start a run and it will appear here.";
    els.runList.append(empty);
    return;
  }
  for (const run of runRecords) {
    const row = document.createElement("div");
    row.className = "run-row";
    row.tabIndex = 0;
    row.setAttribute("role", "button");
    if (run.job_id === selectedRunId) row.classList.add("selected");
    row.title = `${run.job_id}\nUTC: ${run.started_at_utc || "unknown"}`;
    row.addEventListener("click", () => onLoadRun?.(run.job_id, run));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onLoadRun?.(run.job_id, run);
      }
    });

    const main = document.createElement("strong");
    main.textContent = shortRunId(run.job_id);
    const meta = document.createElement("span");
    meta.textContent = `${formatLocalTime(run.started_at_utc)} | ${run.model || "model?"}`;
    const counts = document.createElement("span");
    const accepted = run.accepted_operation_count ?? "-";
    const rejected = run.rejected_operation_count ?? "-";
    const status = run.status || "unknown";
    counts.textContent = `${status} | ${run.runtime_harness_name || run.runtime_harness_id || "harness?"} | ${accepted}/${rejected} ops`;
    if (["queued", "running", "cancelling"].includes(status)) {
      const stop = document.createElement("button");
      stop.type = "button";
      stop.className = "run-row-stop";
      stop.textContent = status === "cancelling" ? "Stopping..." : "Stop";
      stop.disabled = status === "cancelling";
      stop.addEventListener("click", (event) => {
        event.stopPropagation();
        onCancelRun?.(run.job_id, run);
      });
      row.append(main, meta, counts, stop);
    } else {
      row.append(main, meta, counts);
    }
    els.runList.append(row);
  }
}
