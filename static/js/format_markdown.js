import { escapeAttr, escapeHtml } from "./format_html.js";

export function inlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

export function renderMarkdownChunk(text) {
  const lines = String(text || "").split(/\r?\n/);
  const html = [];
  let paragraph = [];
  const flushParagraph = () => {
    if (!paragraph.length) return;
    html.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  };
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      continue;
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (heading) {
      flushParagraph();
      const level = heading[1].length + 2;
      html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }
    const bullet = /^[-*]\s+(.+)$/.exec(trimmed);
    if (bullet) {
      flushParagraph();
      html.push(`<p class="markdown-bullet">• ${inlineMarkdown(bullet[1])}</p>`);
      continue;
    }
    paragraph.push(trimmed);
  }
  flushParagraph();
  return html.join("") || "<p></p>";
}

export function markdownToHtml(text) {
  const raw = String(text || "").trim();
  if (!raw) return "";
  const parts = [];
  const fencePattern = /```(\w+)?\s*\n([\s\S]*?)```/g;
  let cursor = 0;
  let match;
  while ((match = fencePattern.exec(raw)) !== null) {
    if (match.index > cursor) parts.push(renderMarkdownChunk(raw.slice(cursor, match.index)));
    const language = match[1] ? ` data-language="${escapeAttr(match[1])}"` : "";
    parts.push(`<pre class="markdown-code"${language}><code>${escapeHtml(match[2] || "")}</code></pre>`);
    cursor = match.index + match[0].length;
  }
  if (cursor < raw.length) parts.push(renderMarkdownChunk(raw.slice(cursor)));
  return parts.join("");
}
