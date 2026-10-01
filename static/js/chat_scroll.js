export function isScrolledNearBottom(element, tolerance = 32) {
  if (!element) return true;
  return element.scrollHeight - element.scrollTop - element.clientHeight <= tolerance;
}

export function shouldFollowChat(container, tolerance = 96) {
  return Boolean(container && isScrolledNearBottom(container, tolerance));
}

export function maybeFollowChat(container, follow) {
  if (!container || !follow) return;
  container.scrollTop = container.scrollHeight;
}

export function transcriptScrollTopForElement(container, element, topPadding = 14) {
  if (!container || !element) return 0;
  const logRect = container.getBoundingClientRect();
  const elementRect = element.getBoundingClientRect();
  return Math.max(0, container.scrollTop + elementRect.top - logRect.top - topPadding);
}
