import { handleStructuredDecisionEvent } from './stream_structured_decision_events.js';
import { handleStructuredPatchEvent } from './stream_structured_patch_events.js';
import { handleStructuredSnapshotEvent } from './stream_structured_snapshot_events.js';
import { handleStructuredValidationEvent } from './stream_structured_validation_events.js';

export function handleStructuredModelEvent(context, event, payload) {
  if (handleStructuredValidationEvent(context, event, payload)) return true;
  if (handleStructuredPatchEvent(context, event, payload)) return true;
  if (handleStructuredDecisionEvent(context, event, payload)) return true;
  if (handleStructuredSnapshotEvent(context, event, payload)) return true;
  return false;
}
