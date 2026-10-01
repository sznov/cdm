export function sessionChatRenderOptions(message, role) {
  const kind = String(message?.kind || "");
  if (kind === "correction_model_output") {
    return {
      messageId: message.id ? `session-${message.id}` : "",
      label: "Patch clerk output",
      pre: true,
      collapsible: true,
      collapsed: true,
    };
  }
  if (kind === "correction") {
    const automatedCorrection = role === "user" && String(message?.content || "").length > 240;
    return {
      messageId: message.id ? `session-${message.id}` : "",
      label: role === "user" ? (automatedCorrection ? "Correction request" : "You") : "Patch clerk",
      pre: automatedCorrection,
      collapsible: automatedCorrection,
      collapsed: automatedCorrection,
    };
  }
  if (kind === "question") {
    return {
      messageId: message.id ? `session-${message.id}` : "",
      label: role === "user" ? "You" : "LLM",
    };
  }
  return {
    messageId: message.id ? `session-${message.id}` : "",
  };
}
