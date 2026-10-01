import { artifactEls } from "./dom_artifacts.js";
import { decisionsChatEls } from "./dom_decisions_chat.js";
import { modalEls } from "./dom_modals.js";
import { runEls } from "./dom_run.js";
import { runtimeEls } from "./dom_runtime.js";
import { sessionEls } from "./dom_sessions.js";
import { traceEls } from "./dom_trace.js";

export const els = {
  ...runtimeEls,
  ...runEls,
  ...artifactEls,
  ...decisionsChatEls,
  ...traceEls,
  ...sessionEls,
  ...modalEls,
};


