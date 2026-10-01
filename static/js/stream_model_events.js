import { handleStreamModelAnalysisEvent } from './stream_model_analysis_events.js';
import { handleOddOneOutStreamEvent } from './stream_model_odd_one_out_events.js';
import { handleStreamModelRuntimeEvent } from './stream_model_runtime_events.js';
import { handleStructuredModelEvent } from './stream_structured_model_events.js';

const STREAM_MODEL_EVENT_HANDLERS = [
  handleStructuredModelEvent,
  handleOddOneOutStreamEvent,
  handleStreamModelRuntimeEvent,
  handleStreamModelAnalysisEvent,
];

export function handleStreamModelEvent(context, event, payload) {
  return STREAM_MODEL_EVENT_HANDLERS.some((handleEvent) => handleEvent(context, event, payload));
}
