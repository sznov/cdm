export function handleCorrectionSequenceChatEvent(context, event, payload) {
  if (event === "correction_sequence_start") {
    context.appendCorrectionChatMessage("assistant", payload.summary || "Running correction sequence.", { dedupe: true });
    context.setStatus(payload.summary || "Running correction sequence.");
    context.addTraceEntry({
      event,
      agentId: "correctionSequence",
      title: "Correction sequence started",
      summary: payload.summary || "",
      payload,
      status: "running",
    });
    return true;
  }
  if (event === "correction_sequence_step_start") {
    const label = payload.summary || `Correction sequence step ${payload.step_index || ""}`;
    context.appendCorrectionChatMessage("assistant", label, { dedupe: true });
    context.setStatus(label);
    context.addTraceEntry({
      event,
      agentId: "correctionSequence",
      title: `${payload.step_index || "?"}. ${payload.step_name || "Correction step"}`,
      summary: payload.message || label,
      output: payload.message || "",
      payload,
      status: "running",
    });
    return true;
  }
  if (event === "correction_sequence_step_done") {
    context.setStatus(payload.summary || "Correction sequence step complete.");
    context.addTraceEntry({
      event,
      agentId: "correctionSequence",
      title: `Correction step ${payload.step_index || ""} complete`,
      summary: payload.summary || "",
      payload,
      status: payload.rejected_count ? "rejected" : "accepted",
    });
    return true;
  }
  if (event === "correction_sequence_done") {
    context.appendCorrectionChatMessage("assistant", payload.summary || "Correction sequence complete.", { dedupe: true });
    context.setStatus(payload.summary || "Correction sequence complete.");
    context.addTraceEntry({
      event,
      agentId: "correctionSequence",
      title: "Correction sequence complete",
      summary: payload.summary || "",
      payload,
      status: payload.rejected_count ? "rejected" : "accepted",
    });
    context.updateCorrectionChatControls();
    return true;
  }
  return false;
}
