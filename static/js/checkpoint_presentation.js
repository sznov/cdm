export function checkpointPresentation(checkpoint = {}) {
  if (checkpoint.failed) return { kind: "error", label: "Failed", active: false };
  if (checkpoint.cancelled) return { kind: "cancelled", label: "Stopped", active: false };
  if (checkpoint.finalizing) return { kind: "finalizing", label: "Finalizing", active: true };
  if (checkpoint.running) return { kind: "running", label: "Running", active: true };
  return { kind: "complete", label: "Complete", active: false };
}
