// @ts-check

import {
  structuredModelToDot,
} from "./structured_model_dot.js";

/** @type {ReturnType<typeof import("@viz-js/viz").instance> | null} */
let vizInstancePromise = null;

const FORBIDDEN_SVG_ELEMENTS = [
  "script",
  "style",
  "foreignObject",
  "iframe",
  "object",
  "embed",
  "image",
  "use",
  "audio",
  "video",
  "animate",
  "animateMotion",
  "animateTransform",
  "set",
].join(",");

const URL_BEARING_SVG_ATTRIBUTES = new Set([
  "background",
  "clip-path",
  "cursor",
  "data",
  "fill",
  "filter",
  "href",
  "marker-end",
  "marker-mid",
  "marker-start",
  "mask",
  "poster",
  "src",
  "stroke",
  "xlink:href",
]);

function loadVizInstance() {
  if (!vizInstancePromise) {
    vizInstancePromise = import('@viz-js/viz')
      .then(({ instance }) => instance())
      .catch((error) => {
        vizInstancePromise = null;
        throw error;
      });
  }
  return vizInstancePromise;
}

/**
 * Validate once before loading the relatively large renderer and produce the
 * deterministic input used for duplicate-render suppression.
 *
 * @param {unknown} structuredModel
 * @param {{theme?: "light" | "dark"}} [options]
 */
export function prepareStructuredModelDiagram(structuredModel, options = {}) {
  const theme = options.theme === "dark" ? "dark" : "light";
  return {
    dot: structuredModelToDot(structuredModel, { theme }),
    theme,
  };
}

/** @param {SVGSVGElement} source */
function sanitizeSvg(source) {
  if (!source || String(source.tagName || "").toLowerCase() !== "svg") {
    throw new Error("Local diagram renderer did not return an SVG element.");
  }
  const svg = /** @type {SVGSVGElement} */ (source.cloneNode(true));
  for (const forbidden of svg.querySelectorAll(FORBIDDEN_SVG_ELEMENTS)) forbidden.remove();
  for (const element of [svg, ...svg.querySelectorAll("*")]) {
    for (const attribute of [...element.attributes]) {
      const name = attribute.name.toLowerCase();
      const value = attribute.value.trim();
      const unsafeUrl = /(?:\b(?:data|file|https?|javascript):|\/\/|url\s*\()/i.test(value);
      if (
        name.startsWith("on")
        || name === "href"
        || name === "xlink:href"
        || name === "src"
        || (URL_BEARING_SVG_ATTRIBUTES.has(name) && unsafeUrl)
        || ((name === "style" || name === "filter") && /(?:url\s*\(|expression\s*\()/i.test(value))
      ) {
        element.removeAttribute(attribute.name);
      }
    }
  }
  svg.classList.add("diagram-svg-image");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Conceptual model diagram");
  return svg;
}

/**
 * @param {string} dot
 * @param {{isCurrent?: () => boolean}} [options]
 * @returns {Promise<SVGSVGElement | null>}
 */
export async function renderPreparedDiagramSvg(dot, options = {}) {
  const viz = await loadVizInstance();
  if (options.isCurrent && !options.isCurrent()) return null;
  const rendered = viz.renderSVGElement(dot);
  if (options.isCurrent && !options.isCurrent()) return null;
  return sanitizeSvg(rendered);
}
