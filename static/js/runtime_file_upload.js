import { els } from "./dom.js";

function setSpecificationFileStatus(message = "", variant = "") {
  if (!els.specificationFileStatus) return;
  els.specificationFileStatus.textContent = message;
  els.specificationFileStatus.hidden = !message;
  els.specificationFileStatus.classList.toggle("is-error", variant === "error");
}

export function resetSpecificationFileUpload() {
  if (els.specificationFileInput) els.specificationFileInput.value = "";
  setSpecificationFileStatus("");
}

function isTextSpecificationFile(file) {
  if (!file) return false;
  const name = String(file.name || "");
  return /\.(txt|md)$/i.test(name);
}

export function loadSpecificationFromFile(file) {
  if (!file || !els.specification) return;
  if (!isTextSpecificationFile(file)) {
    setSpecificationFileStatus("Choose a .txt or .md file.", "error");
    if (els.specificationFileInput) els.specificationFileInput.value = "";
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    const content = String(reader.result || "").replace(/^\uFEFF/, "");
    els.specification.value = content;
    els.specification.scrollTop = 0;
    els.specification.dispatchEvent(new Event("input", { bubbles: true }));
    setSpecificationFileStatus(file.name ? `Loaded ${file.name}` : "Loaded file.");
    if (els.specificationFileInput) els.specificationFileInput.value = "";
  };
  reader.onerror = () => {
    setSpecificationFileStatus("Could not read file.", "error");
    if (els.specificationFileInput) els.specificationFileInput.value = "";
  };
  reader.readAsText(file);
}
