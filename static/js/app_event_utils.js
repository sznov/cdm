export function on(element, event, handler) {
  if (element) element.addEventListener(event, handler);
}
