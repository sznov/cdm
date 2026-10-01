import {
  createDecisionPatchCard,
  renderDecisionSupersededNote,
} from './decision_cards.js';
import {
  clearConflictingDecisionSelections,
  decisionRoots,
} from './decision_ui_selection.js';

export function createDecisionPatchCardForState(patch, options = {}) {
  return createDecisionPatchCard(patch, {
    ...options,
    isSuperseded: options.isSuperseded,
    model: options.model || null,
    onOptionChange: options.onOptionChange,
  });
}

export function updateDecisionOptionControlsView(options = {}) {
  const elements = options.elements || {};
  const patches = options.patches || [];
  const changedInput =
    options.event?.target?.matches?.('input[type="radio"][data-decision-option]') ? options.event.target : null;
  if (changedInput) clearConflictingDecisionSelections(changedInput, elements);
  const roots = decisionRoots(elements);
  const optionElements = roots.flatMap((root) => [...root.querySelectorAll(".decision-option")]);
  for (const option of optionElements) {
    const input = option.querySelector('input[type="radio"][data-decision-option]');
    option.classList.toggle("is-selected", Boolean(input?.checked));
  }
  for (const card of roots.flatMap((root) => [...root.querySelectorAll(".decision-patch")])) {
    const patch = (patches || []).find((candidate) => String(candidate.id || "") === String(card.dataset.patchId || ""));
    const superseded = Boolean(patch && options.isSuperseded?.(patch));
    card.classList.toggle("is-superseded", superseded);
    renderDecisionSupersededNote(card, superseded);
  }
}

export function updateDecisionPendingIndicatorView(elements = {}, pendingCount = 0) {
  const title = `Decisions (${pendingCount})`;
  if (elements.decisionPendingBadge) {
    elements.decisionPendingBadge.hidden = pendingCount === 0;
    elements.decisionPendingBadge.textContent = String(pendingCount);
    elements.decisionPendingBadge.title = title;
    elements.decisionPendingBadge.setAttribute("aria-label", title);
  }
  if (elements.sessionDecisionNotice) {
    elements.sessionDecisionNotice.hidden = pendingCount === 0;
    elements.sessionDecisionNotice.textContent = `Decisions (${pendingCount})`;
    elements.sessionDecisionNotice.title = title;
    elements.sessionDecisionNotice.setAttribute("aria-label", title);
  }
}
