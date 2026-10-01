import { els } from "./dom.js";

export function localDiagramUrl(url) {
  const candidate = String(url || "");
  return candidate.startsWith("blob:") ? candidate : "";
}

function setDiagramLink(link, url) {
  if (!link) return;
  const localUrl = localDiagramUrl(url);
  if (localUrl) {
    link.href = localUrl;
    link.classList.remove("disabled");
    link.setAttribute("aria-disabled", "false");
    link.removeAttribute("tabindex");
  } else {
    link.href = "#";
    link.classList.add("disabled");
    link.setAttribute("aria-disabled", "true");
    link.setAttribute("tabindex", "-1");
  }
}

export function updateArtifactLinksView(options = {}) {
  const { diagramUrl, onControlStateUpdate } = options;
  setDiagramLink(els.diagramLink, diagramUrl);
  setDiagramLink(els.workingModelDiagramLink, diagramUrl);
  if (typeof onControlStateUpdate === "function") onControlStateUpdate();
}
