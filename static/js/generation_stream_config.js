import { MODEL_GENERATION_EVENTS } from "./generation_stream_model_events.js";
import { PATCH_GENERATION_EVENTS } from "./generation_stream_patch_events.js";

export const CONFIGURED_GENERATION_EVENTS = [
  ...MODEL_GENERATION_EVENTS,
  ...PATCH_GENERATION_EVENTS,
];

export function findConfiguredGenerationEvent(event) {
  return CONFIGURED_GENERATION_EVENTS.find((config) => (
    event === config.start || event === config.delta || event === config.done
  ));
}
