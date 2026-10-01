export function handleOddOneOutStreamEvent(context, event, payload) {
  if (event === "odd_one_out_masked") {
    context.setStatus(payload.summary || "Odd-one-out artifact masked.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "masker",
      title: "Odd-one-out masked",
      summary: payload.summary || "One gold artifact removed before reconstruction.",
      payload,
    });
    return true;
  }
  if (event === "odd_one_out_evaluation") {
    const publicAccepted = Boolean(payload.public_accepted || payload.artifact_validation?.verdict === "accepted");
    const validatorReason = payload.artifact_validation?.reason;
    const retrySuffix = payload.will_retry ? " Retrying with public validator feedback." : "";
    context.setStatus(publicAccepted ? "Public validator accepted odd-one-out artifact." : `${validatorReason || "Public validator rejected odd-one-out artifact."}${retrySuffix}`);
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "validator",
      title: `Odd-one-out public validation ${payload.batch_attempt || 1}`,
      summary: publicAccepted ? "Artifact is structurally valid and plausible without using the hidden answer." : `${validatorReason || "Public validator rejected the artifact."}${retrySuffix}`,
      payload,
      status: publicAccepted ? "accepted" : "rejected",
    });
    return true;
  }
  if (event === "odd_one_out_oracle_evaluation") {
    const matched = Boolean(payload.matches_gold || payload.oracle_evaluation?.matches_gold);
    const reason = payload.oracle_evaluation?.reason;
    context.setStatus(matched ? "Private oracle matched the removed artifact." : "Private oracle scored a miss.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "oracleEvaluator",
      title: `Private oracle score ${payload.batch_attempt || 1}`,
      summary: reason || (matched ? "Predicted artifact matched the removed gold artifact." : "Predicted artifact did not match the removed gold artifact."),
      payload,
      status: matched ? "accepted" : "rejected",
    });
    return true;
  }
  if (event === "odd_one_out_retry_feedback") {
    context.setStatus(payload.summary || "Validator feedback appended for retry.");
    context.addTraceEntry({
      event,
      agentId: payload.agent_id || "validator",
      title: `Retry feedback ${payload.batch_attempt || "?"}`,
      summary: payload.summary || "Validator feedback appended to the live chat history.",
      output: payload.feedback || "",
      payload,
      status: "running",
    });
    return true;
  }
  return false;
}
