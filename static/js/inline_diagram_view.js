import { els } from "./dom.js";
import {
  captureDiagramViewport,
  restoreDiagramViewport,
  scrollDiagramToOrigin,
  setDiagramZoom,
  updateDiagramCentering,
} from "./diagram.js";
import {
  prepareStructuredModelDiagram,
  renderPreparedDiagramSvg,
} from "./local_diagram_renderer.js";

let diagramRenderVersion = 0;
let latestDiagramFingerprint = "";
let currentDiagramObjectUrl = "";

export { updateDiagramControlStateView } from "./diagram_controls_view.js";
export { updateArtifactLinksView } from "./diagram_links_view.js";

function notifyDiagramUrlChanged(options = {}) {
  if (typeof options.onDiagramUrlChange === "function") {
    options.onDiagramUrlChange(currentDiagramObjectUrl);
  }
}

function replaceDiagramObjectUrl(nextUrl = "", options = {}) {
  const previousUrl = currentDiagramObjectUrl;
  currentDiagramObjectUrl = nextUrl;
  if (previousUrl && previousUrl !== nextUrl) URL.revokeObjectURL(previousUrl);
  notifyDiagramUrlChanged(options);
}

export function inlineDiagramObjectUrl() {
  return currentDiagramObjectUrl;
}

export function clearInlineDiagramView(message = "", options = {}) {
  diagramRenderVersion += 1;
  latestDiagramFingerprint = "";
  replaceDiagramObjectUrl("", options);
  if (els.diagramSvg) els.diagramSvg.innerHTML = "";
  if (els.diagramSvgStatus) {
    els.diagramSvgStatus.textContent = message;
    els.diagramSvgStatus.hidden = !message;
  }
}

function diagramNaturalWidth(svg) {
  const viewBox = String(svg.getAttribute("viewBox") || "").trim().split(/\s+/).map(Number);
  if (viewBox.length === 4 && Number.isFinite(viewBox[2]) && viewBox[2] > 0) return viewBox[2];
  const width = Number.parseFloat(String(svg.getAttribute("width") || ""));
  return Number.isFinite(width) && width > 0 ? width : 0;
}

function renderRequestIsCurrent(version, options) {
  return version === diagramRenderVersion
    && (typeof options.isCurrent !== "function" || options.isCurrent());
}

export async function renderInlineDiagramView(structuredModel, options = {}) {
  if (!els.diagramSvg || !els.diagramSvgStatus) return false;
  if (!structuredModel) {
    clearInlineDiagramView("", options);
    return false;
  }
  const preservedViewport = options.viewport || (options.preserveViewport ? captureDiagramViewport() : null);
  let prepared;
  try {
    prepared = prepareStructuredModelDiagram(structuredModel, { theme: options.theme });
  } catch (error) {
    clearInlineDiagramView("", options);
    els.diagramSvgStatus.textContent = `Could not render the local diagram: ${error.message}`;
    els.diagramSvgStatus.hidden = false;
    return false;
  }
  const fingerprint = `${prepared.theme}\n${prepared.dot}`;
  if (
    !options.forceRender
    && fingerprint === latestDiagramFingerprint
    && els.diagramSvg.querySelector(".diagram-svg-image")
  ) {
    const loadedLabel = options.label || "";
    els.diagramSvgStatus.textContent = loadedLabel;
    els.diagramSvgStatus.hidden = !loadedLabel;
    return true;
  }
  const version = diagramRenderVersion + 1;
  diagramRenderVersion = version;
  latestDiagramFingerprint = "";
  replaceDiagramObjectUrl("", options);
  els.diagramSvgStatus.textContent = "Rendering diagram locally...";
  els.diagramSvgStatus.hidden = false;
  els.diagramSvg.innerHTML = "";
  try {
    const svg = await renderPreparedDiagramSvg(prepared.dot, {
      isCurrent: () => renderRequestIsCurrent(version, options),
    });
    if (!svg || !renderRequestIsCurrent(version, options)) return false;
    svg.dataset.naturalWidth = String(diagramNaturalWidth(svg));
    const serialized = new XMLSerializer().serializeToString(svg);
    const objectUrl = URL.createObjectURL(new Blob([serialized], { type: "image/svg+xml" }));
    if (!renderRequestIsCurrent(version, options)) {
      URL.revokeObjectURL(objectUrl);
      return false;
    }
    els.diagramSvg.innerHTML = "";
    els.diagramSvg.append(svg);
    latestDiagramFingerprint = fingerprint;
    replaceDiagramObjectUrl(objectUrl, options);
    setDiagramZoom(preservedViewport ? preservedViewport.zoom : 1);
    if (preservedViewport) {
      restoreDiagramViewport(preservedViewport);
      updateDiagramCentering(svg);
    } else {
      scrollDiagramToOrigin(els.diagramSvg);
    }
    const loadedLabel = options.label || "";
    els.diagramSvgStatus.textContent = loadedLabel;
    els.diagramSvgStatus.hidden = !loadedLabel;
    if (typeof options.onRendered === "function") options.onRendered(svg);
    return true;
  } catch (error) {
    if (!renderRequestIsCurrent(version, options)) return false;
    latestDiagramFingerprint = "";
    replaceDiagramObjectUrl("", options);
    els.diagramSvgStatus.textContent = `Could not render the local diagram: ${error.message}`;
    els.diagramSvgStatus.hidden = false;
    return false;
  }
}

window.addEventListener("pagehide", () => replaceDiagramObjectUrl(""), { once: true });
