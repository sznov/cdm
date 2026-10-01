import { els } from "./dom.js";
import { selectedRuntimeHarnessSummary } from "./runtime_config_selection.js";
import {
  getAppConfig,
  runtimeHarness,
} from "./runtime_state.js";

export function updateRuntimeHarnessBadge() {
  if (!els.runtimeHarnessBadge) return;
  const runtimeName =
    runtimeHarness()?.name ||
    selectedRuntimeHarnessSummary()?.name ||
    getAppConfig().default_runtime_harness_id ||
    "Unavailable";
  els.runtimeHarnessBadge.textContent = `Runtime harness: ${runtimeName}`;
  els.runtimeHarnessBadge.classList.remove("warning");
}
