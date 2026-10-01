import {
  handleCancelRequestedEvent,
  handleRunStartEvent,
} from './stream_lifecycle_start_events.js';
import {
  handlePlantumlPreviewEvent,
  handleWorkingModelEvent,
} from './stream_lifecycle_model_events.js';
import {
  handleCancelledEvent,
  handleDoneEvent,
  handleErrorEvent,
} from './stream_lifecycle_terminal_events.js';

export function handleRunLifecycleEvent(context, event, payload) {
  return (
    handleRunStartEvent(context, event, payload) ||
    handleCancelRequestedEvent(context, event, payload) ||
    handleWorkingModelEvent(context, event, payload) ||
    handlePlantumlPreviewEvent(context, event, payload) ||
    handleDoneEvent(context, event, payload) ||
    handleCancelledEvent(context, event, payload) ||
    handleErrorEvent(context, event, payload)
  );
}
