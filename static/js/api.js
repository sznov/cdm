// @ts-check

/** @typedef {import('../../frontend/src/transport_contracts.js').ApiErrorInit} ApiErrorInit */
/** @typedef {import('../../frontend/src/transport_contracts.js').ApiErrorSurface} ApiErrorSurface */
/** @typedef {import('../../frontend/src/transport_contracts.js').JsonRequestInput} JsonRequestInput */
/** @typedef {import('../../frontend/src/transport_contracts.js').SseEventHandler} SseEventHandler */
/** @typedef {import('../../frontend/src/transport_contracts.js').StreamSseOptions} StreamSseOptions */

/**
 * Stable error surface for non-successful JSON API responses.
 *
 * @implements {ApiErrorSurface}
 */
export class ApiError extends Error {
  /**
   * @param {string} message
   * @param {ApiErrorInit} init
   */
  constructor(message, init) {
    super(message);
    /** @type {'ApiError'} */
    this.name = "ApiError";
    this.status = init.status;
    this.statusText = init.statusText;
    this.url = init.url;
    this.responseText = init.responseText;
    this.payload = init.payload;
  }
}

/**
 * @param {unknown} payload
 * @param {string} fallback
 */
function apiErrorMessage(payload, fallback) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return fallback;
  const record = /** @type {Record<string, unknown>} */ (payload);
  const candidate = record.detail || record.message;
  return candidate ? String(candidate) : fallback;
}

/**
 * @param {string} buffer
 * @param {SseEventHandler} onEvent
 * @returns {string}
 */
export function parseSse(buffer, onEvent) {
  const blocks = buffer.split("\n\n");
  const rest = blocks.pop() ?? "";
  for (const block of blocks) {
    if (!block.trim()) continue;
    let event = "message";
    const data = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim() || "message";
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) continue;
    try {
      onEvent(event, JSON.parse(data.join("\n")));
    } catch (error) {
      console.warn("Could not parse SSE block", error, block);
    }
  }
  return rest;
}

/**
 * @template [TResponse=import('../../frontend/src/run_contracts.js').JsonObject]
 * @param {JsonRequestInput} url
 * @param {RequestInit} [options]
 * @returns {Promise<TResponse | null>}
 */
export async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    let message = text || `HTTP ${response.status}`;
    /** @type {unknown} */
    let payload = null;
    try {
      payload = JSON.parse(text);
      message = apiErrorMessage(payload, message);
    } catch (_) {
      // Keep the raw response text when the server does not return JSON.
    }
    throw new ApiError(message, {
      status: response.status,
      statusText: response.statusText,
      url: response.url || String(url),
      responseText: text,
      payload,
    });
  }
  if (response.status === 204) return null;
  return response.json();
}

/**
 * @param {string} url
 * @param {StreamSseOptions} [options]
 * @returns {Promise<void>}
 */
export function streamSse(url, options = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let buffer = "";
    let seen = 0;
    const onEvent = typeof options.onEvent === "function" ? options.onEvent : () => {};

    xhr.open(options.method || "POST", url, true);
    xhr.setRequestHeader("Content-Type", "application/json");

    xhr.onprogress = () => {
      const chunk = xhr.responseText.slice(seen);
      seen = xhr.responseText.length;
      if (!chunk) return;
      buffer += chunk;
      buffer = parseSse(buffer, onEvent);
    };

    xhr.onload = () => {
      const chunk = xhr.responseText.slice(seen);
      if (chunk) {
        seen = xhr.responseText.length;
        buffer += chunk;
      }
      parseSse(`${buffer}\n\n`, onEvent);

      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(new Error(xhr.responseText || `HTTP ${xhr.status}`));
      }
    };

    xhr.onerror = () => reject(new Error(options.networkErrorMessage || "Network error while streaming."));
    xhr.onabort = () => {
      const error = new Error("Aborted");
      error.name = "AbortError";
      reject(error);
    };

    xhr.send(JSON.stringify(options.payload ?? {}));
  });
}
