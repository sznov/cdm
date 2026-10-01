const DIAGRAM_MIN_ZOOM = 0.05;
const DIAGRAM_MAX_ZOOM = 4;

let diagramZoom = 1;

export function getDiagramZoom() {
  return diagramZoom;
}

export function clampDiagramZoom(nextZoom) {
  return Math.max(DIAGRAM_MIN_ZOOM, Math.min(DIAGRAM_MAX_ZOOM, Number(nextZoom) || 1));
}

export function setDiagramZoomValue(nextZoom) {
  diagramZoom = clampDiagramZoom(nextZoom);
  return diagramZoom;
}
