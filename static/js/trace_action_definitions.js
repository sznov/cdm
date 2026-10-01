import { traceRetryDisabledReason } from './trace_retry_controls.js';
import {
  prepareStructuredModelDiagram,
  renderPreparedDiagramSvg,
} from './local_diagram_renderer.js';

const TRACE_DIAGRAM_URL_LIFETIME_MS = 60_000;

async function openLocalTraceDiagram(context, structuredModel) {
  const placeholder = window.open("about:blank", "_blank");
  if (placeholder) placeholder.opener = null;
  try {
    const prepared = prepareStructuredModelDiagram(structuredModel, {
      theme: document.body.classList.contains("theme-dark") ? "dark" : "light",
    });
    const svg = await renderPreparedDiagramSvg(prepared.dot);
    if (!svg) throw new Error("The local diagram render was cancelled.");
    const serialized = new XMLSerializer().serializeToString(svg);
    const objectUrl = URL.createObjectURL(new Blob([serialized], { type: "image/svg+xml" }));
    if (placeholder && !placeholder.closed) {
      placeholder.location.replace(objectUrl);
    } else {
      const opened = window.open(objectUrl, "_blank", "noreferrer");
      if (!opened) {
        URL.revokeObjectURL(objectUrl);
        context.setStatus("The diagram was rendered locally, but the browser blocked the new tab.");
        return;
      }
    }
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), TRACE_DIAGRAM_URL_LIFETIME_MS);
  } catch (error) {
    if (placeholder && !placeholder.closed) placeholder.close();
    context.setStatus(`Could not open the local diagram: ${error.message}`);
  }
}

export function traceActionDefinitions(context, entry, options = {}) {
  const inputOutputEntry = options.inputOutputEntry || entry;
  const retryEntry = options.retryEntry || entry;
  const stepInput = context.stepInputForTraceEntry(inputOutputEntry);
  const stepOutput = context.stepOutputForTraceEntry(inputOutputEntry);
  const outputIsStreaming = inputOutputEntry?.status === "streaming" || entry?.status === "streaming";
  const stepOutputReady = Boolean(stepOutput) && !outputIsStreaming && !options.forceDisableOutput;
  const artifactsDisabled = Boolean(options.forceDisableArtifacts);
  const artifactsDisabledTitle = "Artifacts are available after this checkpoint finishes";
  const retryDisabledReason = traceRetryDisabledReason(context, retryEntry);
  const structuredModel = entry?.structured_model_snapshot || null;
  const actions = [
    {
      label: "retry",
      title: retryDisabledReason || "Start a new run from the latest model checkpoint at or before this step",
      disabled: Boolean(retryDisabledReason),
      selectEntry: retryEntry,
      handler: () => context.retryFromTraceStep(retryEntry, options.retryContext || {})
        .catch((error) => context.setStatus(`Error: ${error.message}`)),
    },
    {
      label: "input",
      title: "View input consumed by this step",
      disabled: !stepInput,
      handler: () => context.openTextModal("Step input", stepInput),
    },
    {
      label: "output",
      title: stepOutputReady ? "View output produced by this step" : "Output is available after this step finishes",
      disabled: !stepOutputReady,
      handler: () => context.openTextModal("Step output", stepOutput),
    },
    {
      label: "diagram",
      title: artifactsDisabled ? artifactsDisabledTitle : "Open the diagram at this point",
      disabled: artifactsDisabled || !structuredModel,
      handler: () => {
        if (structuredModel) void openLocalTraceDiagram(context, structuredModel);
      },
    },
    {
      label: "puml",
      title: artifactsDisabled ? artifactsDisabledTitle : "View PlantUML source at this point",
      disabled: artifactsDisabled || !entry?.plantuml_snapshot,
      handler: () => context.openTextModal("PlantUML at this step", entry.plantuml_snapshot || ""),
    },
    {
      label: "json",
      title: artifactsDisabled ? artifactsDisabledTitle : "View JSON model at this point",
      disabled: artifactsDisabled || !entry?.working_model_snapshot,
      handler: () => context.openTextModal("JSON IR at this step", entry.working_model_snapshot || {}),
    },
    {
      label: "raw",
      title: artifactsDisabled ? artifactsDisabledTitle : "View raw trace payload",
      disabled: artifactsDisabled,
      handler: () => context.openTextModal("Raw trace payload", entry?.payload || {}),
    },
  ];
  return options.showRetry === false ? actions.filter((action) => action.label !== "retry") : actions;
}
