let getSessionRecords = () => [];
let onChatRailWidthChanged = () => {};

export function configureAppRailDependencies(options = {}) {
  if (typeof options.getSessionRecords === "function") getSessionRecords = options.getSessionRecords;
  if (typeof options.onChatRailWidthChanged === "function") {
    onChatRailWidthChanged = options.onChatRailWidthChanged;
  }
}

export function sessionRecordsForRail() {
  return getSessionRecords();
}

export function notifyChatRailWidthChanged() {
  onChatRailWidthChanged();
}
