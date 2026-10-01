import {
  decisionPatchIsAssumption,
  sortedDecisionPatches,
} from './decision_patch_status.js';
import {
  createDecisionPatchCardForState,
} from './decision_control_view.js';

function createDecisionRailSpecificationCard(specification = "") {
  if (!String(specification).trim()) return null;
  const heading = document.createElement("h3");
  heading.className = "decision-rail-heading decision-spec-heading";
  heading.textContent = "Specification";
  const card = document.createElement("article");
  card.className = "decision-spec-card";
  card.textContent = specification;
  return { card, heading };
}

function createDecisionRailRunInfoCard(runInfo = {}) {
  const rows = [
    ["Harness", runInfo.harness],
    ["Provider", runInfo.provider],
    ["Model", runInfo.model],
  ].filter(([, value]) => String(value || "").trim());
  if (!rows.length) return null;

  const heading = document.createElement("h3");
  heading.className = "decision-rail-heading decision-run-info-heading";
  heading.textContent = "Run";

  const card = document.createElement("article");
  card.className = "decision-run-info-card";
  for (const [label, value] of rows) {
    const row = document.createElement("div");
    row.className = "decision-run-info-row";
    const labelEl = document.createElement("span");
    labelEl.textContent = label;
    const valueEl = document.createElement("strong");
    valueEl.textContent = value;
    row.append(labelEl, valueEl);
    card.append(row);
  }
  return { card, heading };
}

function createDecisionRailEmptyMessage(text) {
  const empty = document.createElement("div");
  empty.className = "decision-rail-empty";
  empty.textContent = text;
  return empty;
}

export function renderDecisionRailView(options = {}) {
  const dock = options.elements?.decisionRail;
  if (!dock) return false;
  const previousSpecHeading = dock.querySelector(".decision-spec-heading");
  const previousSpecCard = dock.querySelector(".decision-spec-card");
  const previousSpecText = previousSpecCard?.textContent ?? "";
  const previousSpecScrollTop = previousSpecCard?.scrollTop ?? 0;
  const previousSpecScrollLeft = previousSpecCard?.scrollLeft ?? 0;
  const previousDockScrollTop = dock.scrollTop;
  const previousDockScrollLeft = dock.scrollLeft;

  const content = document.createDocumentFragment();
  const patches = sortedDecisionPatches(options.patches || []);
  const runInfoCard = createDecisionRailRunInfoCard(options.runInfo || {});
  if (runInfoCard) content.append(runInfoCard.heading, runInfoCard.card);

  const specification = options.specification || "";
  let specCard = null;
  if (String(specification).trim()) {
    specCard = previousSpecCard && previousSpecText === specification
      ? { card: previousSpecCard, heading: previousSpecHeading || document.createElement("h3") }
      : createDecisionRailSpecificationCard(specification);
    specCard.heading.className = "decision-rail-heading decision-spec-heading";
    specCard.heading.textContent = "Specification";
    content.append(specCard.heading, specCard.card);
  }

  const finishRender = () => {
    dock.replaceChildren(content);
    if (specCard?.card && previousSpecText === specification) {
      specCard.card.scrollTop = previousSpecScrollTop;
      specCard.card.scrollLeft = previousSpecScrollLeft;
    }
    dock.scrollTop = previousDockScrollTop;
    dock.scrollLeft = previousDockScrollLeft;
  };

  if (!patches.length) {
    content.append(createDecisionRailEmptyMessage("No decisions or assumptions yet."));
    finishRender();
    return true;
  }
  if (!options.phasesComplete) {
    content.append(createDecisionRailEmptyMessage("Decisions will be available after the final draft."));
    finishRender();
    return true;
  }

  const assumptions = patches.filter(decisionPatchIsAssumption);
  const decisions = patches.filter((patch) => !decisionPatchIsAssumption(patch));
  if (!assumptions.length && !decisions.length) {
    content.append(createDecisionRailEmptyMessage("No decisions or assumptions available."));
    finishRender();
    return true;
  }

  const section = document.createElement("section");
  section.className = "transcript-decision-section";
  section.dataset.transcriptSection = "decisions";

  if (assumptions.length) {
    const heading = document.createElement("h3");
    heading.textContent = "Assumptions";
    section.append(heading);
    for (const patch of assumptions) {
      section.append(createDecisionPatchCardForState(patch, {
        transcript: true,
        readOnly: true,
        model: options.model || null,
        onOptionChange: options.onOptionChange,
        isSuperseded: options.isSuperseded,
      }));
    }
  }

  if (decisions.length) {
    const heading = document.createElement("h3");
    heading.textContent = "Decisions";
    heading.dataset.transcriptSubsectionHeading = "decisions";
    section.append(heading);
    const decisionsGroup = document.createElement("div");
    decisionsGroup.className = "transcript-decisions-group";
    decisionsGroup.dataset.transcriptSubsection = "decisions";
    for (const patch of decisions) {
      decisionsGroup.append(createDecisionPatchCardForState(patch, {
        transcript: true,
        allowControls: options.phasesComplete,
        model: options.model || null,
        onOptionChange: options.onOptionChange,
        isSuperseded: options.isSuperseded,
      }));
    }
    section.append(decisionsGroup);
  }

  content.append(section);
  finishRender();
  return true;
}
