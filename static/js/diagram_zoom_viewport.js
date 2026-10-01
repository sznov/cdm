import { els } from "./dom.js";
import { getDiagramZoom } from "./diagram_zoom_state.js";

function diagramScrollLimits(stage) {
  return {
    left: Math.max(0, stage.scrollWidth - stage.clientWidth),
    top: Math.max(0, stage.scrollHeight - stage.clientHeight),
  };
}

export function captureDiagramViewport() {
  const stage = els.diagramSvg;
  if (!stage) return null;
  const maxScroll = diagramScrollLimits(stage);
  return {
    zoom: getDiagramZoom(),
    scrollLeft: stage.scrollLeft,
    scrollTop: stage.scrollTop,
    scrollLeftRatio: maxScroll.left > 0 ? stage.scrollLeft / maxScroll.left : 0,
    scrollTopRatio: maxScroll.top > 0 ? stage.scrollTop / maxScroll.top : 0,
  };
}

export function restoreDiagramViewport(viewport) {
  const stage = els.diagramSvg;
  if (!stage || !viewport) return;
  const maxScroll = diagramScrollLimits(stage);
  stage.scrollLeft = Math.max(
    0,
    Math.min(maxScroll.left, maxScroll.left > 0 ? maxScroll.left * viewport.scrollLeftRatio : viewport.scrollLeft)
  );
  stage.scrollTop = Math.max(
    0,
    Math.min(maxScroll.top, maxScroll.top > 0 ? maxScroll.top * viewport.scrollTopRatio : viewport.scrollTop)
  );
}
