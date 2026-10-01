import { els } from "./dom.js";

export function headerOverflowCandidates() {
  const sessionActionCandidates = [
    { element: els.deleteSessionButton, label: "Delete session" },
    { element: els.renameSessionButton, label: "Rename title" },
  ];
  return sessionActionCandidates.filter((candidate) => candidate.element);
}

export function isHeaderOverflowCandidateActive(candidate) {
  const element = candidate?.element;
  if (!element) return false;
  return !element.hidden;
}
