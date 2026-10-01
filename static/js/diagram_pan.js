import { els } from "./dom.js";

let diagramPanState = null;

export function beginDiagramPan(event) {
  if (!els.diagramSvg || (event.button != null && event.button !== 0)) return;
  if (!els.diagramSvg.querySelector(".diagram-svg-image")) return;
  event.preventDefault();
  diagramPanState = {
    stage: els.diagramSvg,
    startClientX: event.clientX,
    startClientY: event.clientY,
    startScrollLeft: els.diagramSvg.scrollLeft,
    startScrollTop: els.diagramSvg.scrollTop,
  };
  document.body.classList.add("is-panning-diagram");
  document.addEventListener("pointermove", onDiagramPanMove);
  document.addEventListener("pointerup", endDiagramPan);
  document.addEventListener("pointercancel", endDiagramPan);
}

function onDiagramPanMove(event) {
  if (!diagramPanState) return;
  event.preventDefault();
  const dx = event.clientX - diagramPanState.startClientX;
  const dy = event.clientY - diagramPanState.startClientY;
  diagramPanState.stage.scrollLeft = diagramPanState.startScrollLeft - dx;
  diagramPanState.stage.scrollTop = diagramPanState.startScrollTop - dy;
}

function endDiagramPan() {
  diagramPanState = null;
  document.body.classList.remove("is-panning-diagram");
  document.removeEventListener("pointermove", onDiagramPanMove);
  document.removeEventListener("pointerup", endDiagramPan);
  document.removeEventListener("pointercancel", endDiagramPan);
}
