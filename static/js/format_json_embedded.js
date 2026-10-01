import {
  extractBalancedJsonSegment,
  formatJsonFragmentForDisplay,
} from './format_json_fragment.js';

export function formatLabeledJsonSectionsForDisplay(text) {
  const source = String(text || "");
  const labelPattern = /\b(CURRENT_MODEL|REFERENCE_MODEL|GENERATED_MODEL|CURRENT_JSON|JSON_IR|STRUCTURED_MODEL)\s*:\s*([\[{])/g;
  let cursor = 0;
  let output = "";
  let changed = false;
  let match;
  while ((match = labelPattern.exec(source)) !== null) {
    const bracketIndex = source.indexOf(match[2], match.index);
    const balanced = extractBalancedJsonSegment(source, bracketIndex);
    if (!balanced?.json) continue;
    output += source.slice(cursor, match.index).trimEnd();
    if (output && !output.endsWith("\n")) output += "\n";
    output += `${match[1]}:\n\n\`\`\`json\n${formatJsonFragmentForDisplay(balanced.json)}\n\`\`\``;
    cursor = bracketIndex + balanced.json.length;
    labelPattern.lastIndex = cursor;
    changed = true;
  }
  if (!changed) return source;
  const suffix = source.slice(cursor).trimStart();
  if (suffix) output += `\n\n${suffix}`;
  return output.trim();
}

export function likelyJsonStartIndex(text) {
  const source = String(text || "");
  const fence = /```(?:json)?\s*/i.exec(source);
  if (fence) return { index: fence.index, fenceLength: fence[0].length };
  for (const token of ["{", "["]) {
    const index = source.indexOf(token);
    if (index < 0) continue;
    const rest = source.slice(index).trimStart();
    if (!/^[\[{]/.test(rest)) continue;
    const probe = rest.slice(0, 400);
    if (/^\{\s*"/.test(probe) || /^\[\s*\{/.test(probe) || /"(entities|relationships|attributes|identifier|issues|operations|renames)"\s*:/.test(probe)) {
      return { index, fenceLength: 0 };
    }
  }
  return null;
}

export function formatEmbeddedJsonForDisplay(text) {
  const source = String(text || "").trim();
  if (!source) return "";
  const start = likelyJsonStartIndex(source);
  if (!start) return source;
  const prefix = source.slice(0, start.index).trimEnd();
  let jsonAndSuffix = source.slice(start.index + start.fenceLength);
  let suffix = "";
  const closingFence = jsonAndSuffix.indexOf("```");
  if (closingFence >= 0) {
    suffix = jsonAndSuffix.slice(closingFence + 3).trim();
    jsonAndSuffix = jsonAndSuffix.slice(0, closingFence);
  } else {
    const balanced = extractBalancedJsonSegment(source, start.index);
    if (balanced?.json) {
      jsonAndSuffix = balanced.json;
      suffix = balanced.suffix;
    }
  }
  const formattedJson = formatJsonFragmentForDisplay(jsonAndSuffix);
  if (!formattedJson) return source;
  const parts = [];
  if (prefix) parts.push(prefix);
  parts.push(`\`\`\`json\n${formattedJson}\n\`\`\``);
  if (suffix) parts.push(suffix);
  return parts.join("\n\n");
}
