export function openBuildLogModalView(options = {}) {
  const elements = options.elements || {};
  if (!elements.buildLogModal || !elements.buildLogModalBody) {
    options.openFallback?.();
    return false;
  }
  options.renderBody?.();
  elements.buildLogModal.showModal();
  if (options.scrollToBottom) {
    requestAnimationFrame(() => {
      elements.buildLogModalBody.scrollTop = elements.buildLogModalBody.scrollHeight;
    });
  }
  return true;
}
