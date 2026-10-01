const DISMISSED_RECOVERY_KEY = "cdmapp.dismissedStartupRecovery";

const banner = document.querySelector("#startupRecoveryBanner");
const message = document.querySelector("#startupRecoveryMessage");
const dismissButton = document.querySelector("#dismissStartupRecoveryButton");
let visibleRecoveryId = "";

function dismissedRecoveryId() {
  try {
    return localStorage.getItem(DISMISSED_RECOVERY_KEY) || "";
  } catch {
    return "";
  }
}

function hideRecoveryNotice() {
  if (banner) banner.hidden = true;
}

dismissButton?.addEventListener("click", () => {
  if (visibleRecoveryId) {
    try {
      localStorage.setItem(DISMISSED_RECOVERY_KEY, visibleRecoveryId);
    } catch {
      // The notice still dismisses for this page when storage is unavailable.
    }
  }
  hideRecoveryNotice();
});

/**
 * @param {import('../../frontend/src/transport_contracts.js').StartupRecoverySummary | null | undefined} summary
 */
export function renderStartupRecoveryNotice(summary) {
  visibleRecoveryId = String(summary?.recovery_id || "");
  const text = String(summary?.message || "").trim();
  if (
    !banner ||
    !message ||
    !summary?.occurred ||
    !visibleRecoveryId ||
    !text ||
    dismissedRecoveryId() === visibleRecoveryId
  ) {
    hideRecoveryNotice();
    return;
  }
  message.textContent = text;
  banner.hidden = false;
}
