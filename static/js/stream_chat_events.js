import { handleCorrectionPatchChatEvent } from './stream_chat_correction_patch_events.js';
import { handleCorrectionSequenceChatEvent } from './stream_chat_correction_sequence_events.js';
import { handleQuestionChatEvent } from './stream_chat_question_events.js';

const STREAM_CHAT_EVENT_HANDLERS = [
  handleCorrectionSequenceChatEvent,
  handleQuestionChatEvent,
  handleCorrectionPatchChatEvent,
];

export function handleStreamChatEvent(context, event, payload) {
  return STREAM_CHAT_EVENT_HANDLERS.some((handleEvent) => handleEvent(context, event, payload));
}
