import { handleCorrectionPatchChatLifecycleEvent } from './stream_chat_correction_patch_chat_events.js';
import { handleCorrectionPatchGenerationEvent } from './stream_chat_correction_patch_generation_events.js';

export function handleCorrectionPatchChatEvent(context, event, payload) {
  return handleCorrectionPatchChatLifecycleEvent(context, event, payload) ||
    handleCorrectionPatchGenerationEvent(context, event, payload);
}
