const DEFAULT_SESSION_MEASURED_WIDTH = 220;

function measuredTextWidth(context, element) {
  if (!element) return 0;
  const style = window.getComputedStyle(element);
  context.font = style.font || `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
  return context.measureText(element.textContent || "").width;
}

function px(value) {
  return Number.parseFloat(value) || 0;
}

export function sessionRailContentFitWidth(options = {}) {
  const { hardMaxWidth, sessionList, sessionRecords = [] } = options;
  if (!sessionList || !sessionRecords.length) return DEFAULT_SESSION_MEASURED_WIDTH;
  const rows = Array.from(sessionList.querySelectorAll(".session-row"));
  if (!rows.length) return DEFAULT_SESSION_MEASURED_WIDTH;
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  if (!context) return DEFAULT_SESSION_MEASURED_WIDTH;
  let widestContent = 0;
  for (const row of rows) {
    const title = row.querySelector("strong");
    const subtitle = row.querySelector("span:not(.session-progress-indicator)");
    widestContent = Math.max(
      widestContent,
      measuredTextWidth(context, title),
      measuredTextWidth(context, subtitle),
    );
  }
  const railStyle = window.getComputedStyle(document.querySelector(".session-rail") || document.documentElement);
  const rowStyle = window.getComputedStyle(rows[0]);
  const chromeWidth =
    px(railStyle.paddingLeft) +
    px(railStyle.paddingRight) +
    px(rowStyle.paddingLeft) +
    px(rowStyle.paddingRight) +
    px(rowStyle.borderLeftWidth) +
    px(rowStyle.borderRightWidth) +
    14;
  return Math.ceil(Math.min(hardMaxWidth, widestContent + chromeWidth));
}

export function appRailWidthBounds(kind, options = {}) {
  const { sessionList, sessionRecords = [] } = options;
  const viewportWidth = window.innerWidth || 1200;
  const minWidth = 156;
  const maxByViewport = Math.round(viewportWidth * 0.34);
  const hardMaxWidth = Math.max(minWidth, Math.min(420, maxByViewport));
  const contentMaxWidth =
    kind === "session"
      ? sessionRailContentFitWidth({ hardMaxWidth, sessionList, sessionRecords })
      : hardMaxWidth;
  const maxWidth = Math.max(minWidth, Math.min(hardMaxWidth, contentMaxWidth));
  return { minWidth, maxWidth };
}
