import { fetchJson } from "./api.js";
import { els } from "./dom.js";

let correctionTemplates = [];
let defaultTemplateIdGetter = () => "";
let onDefaultTemplateId = () => {};
let onTemplatesChanged = () => {};

export function configureCorrectionTemplates(options = {}) {
  if (typeof options.getDefaultTemplateId === "function") {
    defaultTemplateIdGetter = options.getDefaultTemplateId;
  }
  if (typeof options.onDefaultTemplateId === "function") {
    onDefaultTemplateId = options.onDefaultTemplateId;
  }
  if (typeof options.onTemplatesChanged === "function") {
    onTemplatesChanged = options.onTemplatesChanged;
  }
}

export function getCorrectionTemplates() {
  return correctionTemplates;
}

export function selectedCorrectionTemplate(templateId = els.correctionTemplateSelect?.value) {
  return correctionTemplates.find((candidate) => candidate.id === templateId) || null;
}

export function renderCorrectionTemplates() {
  if (!els.correctionTemplateSelect) return;
  const previous = els.correctionTemplateSelect.value;
  els.correctionTemplateSelect.innerHTML = "";
  for (const template of correctionTemplates) {
    const option = document.createElement("option");
    option.value = template.id;
    option.textContent = template.name || template.id;
    els.correctionTemplateSelect.append(option);
  }
  const preferred = previous || defaultTemplateIdGetter();
  if (preferred && correctionTemplates.some((template) => template.id === preferred)) {
    els.correctionTemplateSelect.value = preferred;
  }
  updateCorrectionTemplateDescription();
  onTemplatesChanged();
}

export function updateCorrectionTemplateDescription() {
  if (!els.correctionTemplateDescription) return;
  const template = selectedCorrectionTemplate();
  els.correctionTemplateDescription.innerHTML = "";
  if (!template) {
    els.correctionTemplateDescription.textContent = "No correction template selected.";
    return;
  }
  if (template.description) {
    const summary = document.createElement("p");
    summary.className = "correction-template-summary";
    summary.textContent = template.description;
    els.correctionTemplateDescription.append(summary);
  }
  const steps = (template.steps || []).filter((step) => step.message || step.name || step.id);
  if (!steps.length) return;
  const list = document.createElement("ol");
  list.className = "correction-template-steps";
  for (const step of steps) {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = step.name || step.id || "Correction step";
    item.append(title);
    if (step.message) {
      const message = document.createElement("span");
      message.textContent = step.message;
      item.append(message);
    }
    list.append(item);
  }
  els.correctionTemplateDescription.append(list);
}

export async function loadCorrectionTemplates() {
  if (!els.correctionTemplateSelect) return { templates: correctionTemplates };
  const payload = await fetchJson("/api/correction-templates");
  correctionTemplates = payload.templates || [];
  if (payload.default_template_id) onDefaultTemplateId(payload.default_template_id);
  renderCorrectionTemplates();
  return payload;
}
