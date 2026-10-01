import { els } from "./dom.js";

export function diagramNaturalWidth(image) {
  const naturalWidth = Number(image?.naturalWidth || 0);
  if (Number.isFinite(naturalWidth) && naturalWidth > 0) return naturalWidth;
  const dataWidth = Number(image?.dataset?.naturalWidth || 0);
  if (Number.isFinite(dataWidth) && dataWidth > 0) return dataWidth;
  const { width: availableWidth } = diagramViewportSize();
  return Math.max(1, availableWidth || image?.offsetWidth || 1);
}

export function diagramViewportSize() {
  const stage = els.diagramSvg;
  if (!stage) return { width: 0, height: 0 };
  const stageStyle = getComputedStyle(stage);
  return {
    width: Math.max(
      0,
      stage.clientWidth - parseFloat(stageStyle.paddingLeft || "0") - parseFloat(stageStyle.paddingRight || "0")
    ),
    height: Math.max(
      0,
      stage.clientHeight - parseFloat(stageStyle.paddingTop || "0") - parseFloat(stageStyle.paddingBottom || "0")
    ),
  };
}

function diagramStagePadding(stage = els.diagramSvg) {
  if (!stage) return { left: 0, top: 0 };
  const stageStyle = getComputedStyle(stage);
  return {
    left: parseFloat(stageStyle.paddingLeft || "0") || 0,
    top: parseFloat(stageStyle.paddingTop || "0") || 0,
  };
}

function diagramStageOriginScroll(stage = els.diagramSvg) {
  if (!stage) return { left: 0, top: 0 };
  const padding = diagramStagePadding(stage);
  const maxScrollLeft = Math.max(0, stage.scrollWidth - stage.clientWidth);
  const maxScrollTop = Math.max(0, stage.scrollHeight - stage.clientHeight);
  return {
    left: Math.max(0, Math.min(maxScrollLeft, padding.left)),
    top: Math.max(0, Math.min(maxScrollTop, padding.top)),
  };
}

export function scrollDiagramToOrigin(stage = els.diagramSvg) {
  if (!stage) return;
  const origin = diagramStageOriginScroll(stage);
  stage.scrollLeft = origin.left;
  stage.scrollTop = origin.top;
}

export function updateDiagramCentering(image = null) {
  const stage = els.diagramSvg;
  const diagram = image || stage?.querySelector(".diagram-svg-image");
  if (!stage || !diagram) return;
  diagram.style.marginLeft = "0px";
  diagram.style.marginTop = "0px";
  const { width: availableWidth, height: availableHeight } = diagramViewportSize();
  const horizontalMargin = Math.max(0, (availableWidth - diagram.offsetWidth) / 2);
  const verticalMargin = Math.max(0, (availableHeight - diagram.offsetHeight) / 2);
  diagram.style.marginLeft = `${horizontalMargin}px`;
  diagram.style.marginTop = `${verticalMargin}px`;
  const origin = diagramStageOriginScroll(stage);
  if (diagram.offsetWidth <= availableWidth) stage.scrollLeft = origin.left;
  if (diagram.offsetHeight <= availableHeight) stage.scrollTop = origin.top;
}
