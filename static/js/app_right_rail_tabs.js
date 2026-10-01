let activeRightRailTab = "progress";

export function setRightRailTab(context, tabId) {
  const { elements } = context;
  const next = ["progress", "decisions"].includes(tabId) ? tabId : "progress";
  activeRightRailTab = next;
  for (const button of elements.rightRailTabs || []) {
    const active = button.dataset.railTab === next;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  }
  for (const panel of elements.rightRailPanels || []) {
    const active = panel.dataset.railPanel === next;
    panel.classList.toggle("is-active", active);
    panel.hidden = !active;
  }
}

export function currentRightRailTab() {
  return activeRightRailTab;
}
