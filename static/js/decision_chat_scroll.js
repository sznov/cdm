import {
  appRailCollapsed,
  setAppRailCollapsed,
} from './layout.js';

export function scrollToTranscriptDecisions(context) {
  const dock = context.elements.decisionRail;
  if (!dock) return;
  if (appRailCollapsed("chat")) {
    setAppRailCollapsed("chat", false);
  }
  window.requestAnimationFrame(() => {
    const section = dock.querySelector(".transcript-decision-section");
    const decisionsGroup = dock.querySelector("[data-transcript-subsection='decisions']");
    const target =
      dock.querySelector("[data-transcript-subsection-heading='decisions']") ||
      (decisionsGroup?.previousElementSibling?.tagName === "H3" ? decisionsGroup.previousElementSibling : null) ||
      decisionsGroup ||
      section;
    if (!target) {
      dock.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }
    target.setAttribute("tabindex", "-1");
    const dockRect = dock.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const nextScrollTop = dock.scrollTop + targetRect.top - dockRect.top - 8;
    dock.scrollTop = Math.max(0, nextScrollTop);
    dock.scrollIntoView({ behavior: "smooth", block: "nearest" });
    target.focus({ preventScroll: true });
    section?.classList.add("is-highlighted");
    window.setTimeout(() => section?.classList.remove("is-highlighted"), 1000);
  });
}
