import { els } from "./dom.js";
import { formatJson } from "./format.js";

let currentTextModalFilename = "details.txt";
let currentTextModalMimeType = "text/plain;charset=utf-8";
let statusSink = () => {};

export function configureTextModal(options = {}) {
  if (typeof options.setStatus === "function") statusSink = options.setStatus;
}

function textModalValue() {
  return els.textModalBody?.value || "";
}

function sanitizeDownloadFilename(value, fallback = "details.txt") {
  const cleaned = String(value || "")
    .trim()
    .replace(/\s+/g, "-")
    .replace(/[^a-zA-Z0-9._-]+/g, "")
    .replace(/^-+|-+$/g, "");
  return cleaned || fallback;
}

function textModalFilenameFor(title, value) {
  const text = typeof value === "string" ? value : formatJson(value);
  const lowerTitle = String(title || "").toLowerCase();
  if (lowerTitle.includes("current plantuml")) return "working-model.plantuml";
  if (lowerTitle.includes("plantuml")) return `${sanitizeDownloadFilename(title || "plantuml", "plantuml")}.plantuml`;
  if (lowerTitle.includes("current json ir")) return "working-model.json";
  if (lowerTitle.includes("json") || /^\s*[{[]/.test(text)) return `${sanitizeDownloadFilename(title || "details", "details")}.json`;
  return `${sanitizeDownloadFilename(title || "details", "details")}.txt`;
}

export function openTextModal(title, value, options = {}) {
  if (!els.textModal || !els.textModalTitle || !els.textModalBody) return;
  const text = typeof value === "string" ? value : formatJson(value);
  els.textModalTitle.textContent = title || "Details";
  els.textModalBody.value = text;
  currentTextModalFilename = sanitizeDownloadFilename(options.filename || textModalFilenameFor(title, value), "details.txt");
  currentTextModalMimeType = options.mimeType || (currentTextModalFilename.endsWith(".json") ? "application/json;charset=utf-8" : "text/plain;charset=utf-8");
  els.textModal.showModal();
  requestAnimationFrame(() => {
    els.textModalBody?.focus();
    els.textModalBody?.setSelectionRange(0, 0);
  });
}

export async function copyTextModalContent() {
  const text = textModalValue();
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    els.textModalBody?.focus();
    els.textModalBody?.select();
    document.execCommand("copy");
  }
  statusSink("Copied modal text.");
}

export function downloadTextModalContent() {
  const text = textModalValue();
  const blob = new Blob([text], { type: currentTextModalMimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = currentTextModalFilename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function selectTextModalBody() {
  if (!els.textModalBody) return;
  els.textModalBody.focus();
  els.textModalBody.select();
}

export function handleTextModalKeydown(event) {
  if (!els.textModal?.open) return;
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") {
    event.preventDefault();
    selectTextModalBody();
  }
}
