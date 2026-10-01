import { fetchJson } from "./api.js";

const HEALTH_POLL_INTERVAL_MS = 5000;
const banner = document.querySelector("#runtimeHealthBanner");
const message = document.querySelector("#runtimeHealthMessage");
const dismissButton = document.querySelector("#dismissRuntimeHealthButton");

let dismissedSignature = "";
let pollTimer = null;
let pollInFlight = false;

function runtimeNoticeSignature(coordinator) {
  const runIds = Array.isArray(coordinator?.degraded_runs)
    ? coordinator.degraded_runs.map((entry) => String(entry?.run_id || "")).sort()
    : [];
  const admission =
    coordinator?.admission === "paused"
      ? `paused:${Number(coordinator?.admission_generation || 0)}:${String(
          coordinator?.admission_expires_at_utc || "",
        )}`
      : String(coordinator?.admission || "unknown");
  return `${admission}:${Number(coordinator?.degraded_count || 0)}:${runIds.join(",")}`;
}

function hideRuntimeHealthNotice() {
  if (banner) banner.hidden = true;
}

dismissButton?.addEventListener("click", () => {
  dismissedSignature = String(banner?.dataset.degradedSignature || "");
  hideRuntimeHealthNotice();
});

/**
 * @param {import('../../frontend/src/transport_contracts.js').ApplicationHealth | null | undefined} health
 */
export function renderRuntimeHealthNotice(health) {
  const coordinator = health?.coordinator;
  const degradedCount = Number(coordinator?.degraded_count || 0);
  const persistenceDegraded =
    coordinator?.status === "degraded" && degradedCount > 0;
  const admissionPaused = coordinator?.admission === "paused";
  if (!banner || !message || (!persistenceDegraded && !admissionPaused)) {
    hideRuntimeHealthNotice();
    return;
  }
  const signature = runtimeNoticeSignature(coordinator);
  banner.dataset.degradedSignature = signature;
  if (signature === dismissedSignature) {
    hideRuntimeHealthNotice();
    return;
  }
  const notices = [];
  if (persistenceDegraded) {
    const noun = degradedCount === 1 ? "run" : "runs";
    notices.push(
      `Local terminal persistence needs recovery for ${degradedCount} ${noun}. ` +
        "Provider work has stopped; restart the app to repair its lifecycle history.",
    );
  }
  if (admissionPaused) {
    notices.push(
      "New model work is temporarily paused. " +
        "If this persists, restart the app.",
    );
  }
  message.textContent = notices.join(" ");
  banner.hidden = false;
}

export async function pollRuntimeHealth() {
  if (pollInFlight) return;
  pollInFlight = true;
  try {
    const health = await fetchJson("/api/health", { cache: "no-store" });
    renderRuntimeHealthNotice(health);
  } catch {
    // Other application controls expose a backend outage. Do not replace a
    // precise degraded-state warning with speculation after a failed poll.
  } finally {
    pollInFlight = false;
  }
}

export function startRuntimeHealthPolling() {
  if (pollTimer !== null) return;
  void pollRuntimeHealth();
  pollTimer = setInterval(() => {
    void pollRuntimeHealth();
  }, HEALTH_POLL_INTERVAL_MS);
}
