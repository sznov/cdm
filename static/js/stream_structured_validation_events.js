import { handleStructuredCoverageEvent } from './stream_structured_coverage_events.js';
import { handleStructuredDraftEvent } from './stream_structured_draft_events.js';
import { handleStructuredPromptEvent } from './stream_structured_prompt_events.js';

const STRUCTURED_VALIDATION_EVENT_HANDLERS = [
  handleStructuredPromptEvent,
  handleStructuredDraftEvent,
  handleStructuredCoverageEvent,
];

export function handleStructuredValidationEvent(context, event, payload) {
  return STRUCTURED_VALIDATION_EVENT_HANDLERS.some((handleEvent) => handleEvent(context, event, payload));
}
