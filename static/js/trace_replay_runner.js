function defaultShouldContinue() {
  return true;
}

function defaultYieldToBrowser() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

export async function replayTraceLog(records = [], options = {}) {
  const {
    appendDelta = () => {},
    handleEvent = () => {},
    isDeltaEvent = () => false,
    batchDeltas = false,
    shouldContinue = defaultShouldContinue,
    startIndex = 0,
    yieldEvery = 0,
    yieldToBrowser = defaultYieldToBrowser,
  } = options;
  if (!Array.isArray(records) || !records.length || startIndex >= records.length) {
    return { completed: true, replayedCount: 0, skippedDeltaCount: 0 };
  }
  let skippedDeltaCount = 0;
  let replayedCount = 0;
  let bufferedDelta = "";
  let bufferedDeltaRecord = null;
  let bufferedDeltaIndex = -1;
  const flushBufferedDelta = () => {
    if (!bufferedDelta) return;
    appendDelta(bufferedDelta, bufferedDeltaRecord, bufferedDeltaIndex);
    bufferedDelta = "";
    bufferedDeltaRecord = null;
    bufferedDeltaIndex = -1;
  };
  for (let traceIndex = Math.max(0, Number(startIndex) || 0); traceIndex < records.length; traceIndex += 1) {
    if (!shouldContinue()) return { completed: false, replayedCount, skippedDeltaCount };
    if (yieldEvery && traceIndex > startIndex && traceIndex % yieldEvery === 0) {
      flushBufferedDelta();
      await yieldToBrowser();
    }
    if (!shouldContinue()) return { completed: false, replayedCount, skippedDeltaCount };
    const record = records[traceIndex];
    if (!record || !record.event) continue;
    replayedCount += 1;
    if (isDeltaEvent(record.event)) {
      skippedDeltaCount += 1;
      if (batchDeltas) {
        bufferedDelta += record.payload?.delta || "";
        bufferedDeltaRecord = record;
        bufferedDeltaIndex = traceIndex;
      } else {
        appendDelta(record.payload?.delta || "", record, traceIndex);
      }
      continue;
    }
    flushBufferedDelta();
    handleEvent(record.event, {
      ...(record.payload || {}),
      __trace_index: traceIndex,
      __trace_timestamp_utc: record.timestamp_utc,
      __replay: true,
    });
  }
  flushBufferedDelta();
  return { completed: true, replayedCount, skippedDeltaCount };
}
