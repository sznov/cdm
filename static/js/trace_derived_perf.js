export function perfStart() {
  return typeof performance !== "undefined" && performance.now ? performance.now() : Date.now();
}

export function perfLog(label, startedAt, detail = {}) {
  const now = typeof performance !== "undefined" && performance.now ? performance.now() : Date.now();
  const durationMs = Math.round(now - startedAt);
  console.debug(`[perf] ${label}: ${durationMs}ms`, detail);
}

export function yieldToBrowser() {
  return new Promise((resolve) => {
    if (typeof requestIdleCallback === "function") {
      requestIdleCallback(() => resolve(), { timeout: 50 });
    } else {
      setTimeout(resolve, 0);
    }
  });
}
