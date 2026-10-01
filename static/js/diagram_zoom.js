import { els } from "./dom.js";
import {
  diagramNaturalWidth,
  diagramViewportSize,
  scrollDiagramToOrigin,
  updateDiagramCentering,
} from "./diagram_geometry.js";
import {
  clampDiagramZoom,
  getDiagramZoom,
  setDiagramZoomValue,
} from "./diagram_zoom_state.js";

export { getDiagramZoom } from "./diagram_zoom_state.js";
export {
  captureDiagramViewport,
  restoreDiagramViewport,
} from "./diagram_zoom_viewport.js";

export function applyDiagramZoom() {
  const image = els.diagramSvg?.querySelector(".diagram-svg-image");
  if (!image) return;
  const baseWidth = diagramNaturalWidth(image);
  image.style.width = `${Math.max(1, baseWidth * getDiagramZoom())}px`;
  image.style.transform = "none";
  updateDiagramCentering(image);
}

export function setDiagramZoom(nextZoom, options = {}) {
  const stage = els.diagramSvg;
  const previousZoom = getDiagramZoom();
  const next = clampDiagramZoom(nextZoom);
  const shouldAnchor =
    stage &&
    stage.querySelector(".diagram-svg-image") &&
    Number.isFinite(options.anchorClientX) &&
    Number.isFinite(options.anchorClientY) &&
    previousZoom > 0 &&
    next !== previousZoom;
  if (shouldAnchor) {
    const image = stage.querySelector(".diagram-svg-image");
    const beforeImageRect = image.getBoundingClientRect();
    const anchorImageX = options.anchorClientX - beforeImageRect.left;
    const anchorImageY = options.anchorClientY - beforeImageRect.top;
    const ratio = next / previousZoom;
    setDiagramZoomValue(next);
    applyDiagramZoom();
    const afterImageRect = image.getBoundingClientRect();
    stage.scrollLeft += afterImageRect.left + anchorImageX * ratio - options.anchorClientX;
    stage.scrollTop += afterImageRect.top + anchorImageY * ratio - options.anchorClientY;
    updateDiagramCentering(image);
    return;
  }
  setDiagramZoomValue(next);
  applyDiagramZoom();
}

export function fitDiagramToViewport() {
  const stage = els.diagramSvg;
  const image = stage?.querySelector(".diagram-svg-image");
  if (!stage || !image) return;
  const { width: availableWidth, height: availableHeight } = diagramViewportSize();
  const imageRect = image.getBoundingClientRect();
  if (availableWidth <= 0 || availableHeight <= 0 || imageRect.width <= 0 || imageRect.height <= 0) return;
  const fitRatio = Math.min(availableWidth / imageRect.width, availableHeight / imageRect.height);
  if (!Number.isFinite(fitRatio) || fitRatio <= 0) return;
  setDiagramZoomValue(getDiagramZoom() * fitRatio);
  applyDiagramZoom();
  scrollDiagramToOrigin(stage);
  updateDiagramCentering(image);
}

export function resetDiagramZoom() {
  const stage = els.diagramSvg;
  setDiagramZoom(1);
  if (!stage) return;
  scrollDiagramToOrigin(stage);
  updateDiagramCentering();
}

export function onDiagramWheel(event) {
  if (!event.ctrlKey && !event.metaKey) return;
  if (!els.diagramSvg?.querySelector(".diagram-svg-image")) return;
  event.preventDefault();
  const zoomFactor = Math.exp(-event.deltaY * 0.0015);
  setDiagramZoom(getDiagramZoom() * zoomFactor, {
    anchorClientX: event.clientX,
    anchorClientY: event.clientY,
  });
}
