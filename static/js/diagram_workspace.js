import { els } from "./dom.js";
import { updateDiagramCentering } from "./diagram_geometry.js";

const DIAGRAM_HEIGHT_STORAGE_KEY = "cdmapp.diagramWorkspaceHeight";

let diagramWorkspaceResizeState = null;

function diagramWorkspaceHeightBounds() {
  const shell = document.querySelector(".codex-shell");
  const shellHeight = shell?.getBoundingClientRect().height || window.innerHeight || 800;
  const minHeight = Math.round(Math.max(150, Math.min(260, shellHeight * 0.24)));
  const mainMinHeight = Math.round(Math.max(210, Math.min(360, shellHeight * 0.38)));
  const maxHeight = Math.max(minHeight, Math.round(shellHeight - mainMinHeight));
  return { minHeight, maxHeight };
}

function applyDiagramWorkspaceHeight(height, options = {}) {
  const numeric = Number(height);
  if (!Number.isFinite(numeric) || numeric <= 0) return;
  const { minHeight, maxHeight } = diagramWorkspaceHeightBounds();
  const clamped = Math.max(minHeight, Math.min(maxHeight, Math.round(numeric)));
  document.documentElement.style.setProperty("--diagram-workspace-height", `${clamped}px`);
  if (options.persist !== false) {
    localStorage.setItem(DIAGRAM_HEIGHT_STORAGE_KEY, String(clamped));
  }
  updateDiagramCentering();
}

function readStoredDiagramWorkspaceHeight() {
  return Number(localStorage.getItem(DIAGRAM_HEIGHT_STORAGE_KEY));
}

export function restoreDiagramWorkspaceHeight() {
  const stored = readStoredDiagramWorkspaceHeight();
  if (Number.isFinite(stored) && stored > 0) applyDiagramWorkspaceHeight(stored, { persist: false });
}

export function clampDiagramWorkspaceHeight() {
  const current =
    els.diagramWorkspace?.getBoundingClientRect().height ||
    readStoredDiagramWorkspaceHeight() ||
    0;
  if (current > 0) applyDiagramWorkspaceHeight(current, { persist: false });
}

export function beginDiagramWorkspaceResize(event) {
  if (!els.diagramWorkspace || event.button !== 0) return;
  event.preventDefault();
  diagramWorkspaceResizeState = {
    startClientY: event.clientY,
    startHeight: els.diagramWorkspace.getBoundingClientRect().height,
  };
  document.body.classList.add("is-resizing-working-model");
  document.addEventListener("pointermove", onDiagramWorkspaceResizeMove);
  document.addEventListener("pointerup", endDiagramWorkspaceResize);
  document.addEventListener("pointercancel", endDiagramWorkspaceResize);
}

function onDiagramWorkspaceResizeMove(event) {
  if (!diagramWorkspaceResizeState) return;
  event.preventDefault();
  applyDiagramWorkspaceHeight(
    diagramWorkspaceResizeState.startHeight - (event.clientY - diagramWorkspaceResizeState.startClientY),
    { persist: false }
  );
}

function endDiagramWorkspaceResize() {
  if (diagramWorkspaceResizeState && els.diagramWorkspace) {
    applyDiagramWorkspaceHeight(els.diagramWorkspace.getBoundingClientRect().height);
  }
  diagramWorkspaceResizeState = null;
  document.body.classList.remove("is-resizing-working-model");
  document.removeEventListener("pointermove", onDiagramWorkspaceResizeMove);
  document.removeEventListener("pointerup", endDiagramWorkspaceResize);
  document.removeEventListener("pointercancel", endDiagramWorkspaceResize);
}

export function resizeDiagramWorkspaceBy(delta) {
  const current =
    els.diagramWorkspace?.getBoundingClientRect().height ||
    readStoredDiagramWorkspaceHeight() ||
    Math.round((window.innerHeight || 800) * 0.44);
  applyDiagramWorkspaceHeight(current + delta);
}
