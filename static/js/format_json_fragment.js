export function formatJson(value) {
  return JSON.stringify(value, null, 2);
}

export function prettyPrintJsonFragment(fragment) {
  const source = String(fragment || "").trim();
  if (!source) return "";
  let output = "";
  let indent = 0;
  let inString = false;
  let escaped = false;
  const appendIndent = () => {
    output += "  ".repeat(Math.max(0, indent));
  };
  const trimTrailingSpace = () => {
    output = output.replace(/[ \t]+$/g, "");
  };
  for (const char of source) {
    if (inString) {
      output += char;
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === "\"") {
        inString = false;
      }
      continue;
    }
    if (/\s/.test(char)) continue;
    if (char === "\"") {
      inString = true;
      output += char;
      continue;
    }
    if (char === "{" || char === "[") {
      trimTrailingSpace();
      output += char;
      indent += 1;
      output += "\n";
      appendIndent();
      continue;
    }
    if (char === "}" || char === "]") {
      indent = Math.max(0, indent - 1);
      trimTrailingSpace();
      if (!output.endsWith("\n")) output += "\n";
      appendIndent();
      output += char;
      continue;
    }
    if (char === ",") {
      trimTrailingSpace();
      output += ",\n";
      appendIndent();
      continue;
    }
    if (char === ":") {
      trimTrailingSpace();
      output += ": ";
      continue;
    }
    output += char;
  }
  return output.trimEnd();
}

export function formatJsonFragmentForDisplay(fragment) {
  const source = String(fragment || "")
    .replace(/^\s*```(?:json)?\s*/i, "")
    .replace(/\s*```\s*$/i, "")
    .trim();
  if (!source) return "";
  try {
    return formatJson(JSON.parse(source));
  } catch {
    return prettyPrintJsonFragment(source);
  }
}

export function extractBalancedJsonSegment(source, startIndex) {
  const text = String(source || "");
  const opening = text[startIndex];
  const closing = opening === "{" ? "}" : opening === "[" ? "]" : "";
  if (!closing) return null;
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = startIndex; index < text.length; index += 1) {
    const char = text[index];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === "\"") {
        inString = false;
      }
      continue;
    }
    if (char === "\"") {
      inString = true;
      continue;
    }
    if (char === opening) {
      depth += 1;
    } else if (char === closing) {
      depth -= 1;
      if (depth === 0) {
        return {
          json: text.slice(startIndex, index + 1),
          suffix: text.slice(index + 1).trim(),
        };
      }
    }
  }
  return {
    json: text.slice(startIndex),
    suffix: "",
  };
}
