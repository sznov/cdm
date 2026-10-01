export function setScrollableTextContent(element, text, options = {}) {
  if (!element) return false;
  const shouldFollow = options.isScrolledNearBottom || (() => true);
  const follow = options.follow ?? shouldFollow(element);
  const previousScrollTop = element.scrollTop;
  element.textContent = text || "";
  element.scrollTop = follow ? element.scrollHeight : previousScrollTop;
  return follow;
}

export function appendScrollableText(element, text, options = {}) {
  if (!element) return false;
  const shouldFollow = options.isScrolledNearBottom || (() => true);
  const follow = options.follow ?? shouldFollow(element);
  element.append(document.createTextNode(text || ""));
  if (follow) element.scrollTop = element.scrollHeight;
  return follow;
}
