export function renderDecisionSupersededNote(card, superseded) {
  if (!card) return;
  let note = card.querySelector(".decision-superseded-note");
  if (superseded) {
    if (!note) {
      note = document.createElement("div");
      note.className = "decision-superseded-note";
      note.textContent = "Covered by another identifier decision.";
      card.querySelector(".decision-patch-body")?.append(note);
    }
  } else {
    note?.remove();
  }
}
