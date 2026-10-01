import {
  restoreDiagramWorkspaceHeight,
} from './diagram.js';
import {
  configureLayout,
  restoreAppRailLayout,
} from './layout.js';
import {
  scheduleDiagramControlPlacement,
  scheduleHeaderOverflowUpdate,
  setupHeaderLayoutObserver,
} from './header_layout.js';
import {
  configureRuntimeControls,
  loadConfig,
  loadHarnesses,
  patchAppConfig,
  triggerStartupProviderModelRefreshes,
} from './runtime.js';
import {
  configureTheme,
  initTheme,
} from './theme.js';
import {
  configureCorrectionTemplates,
  loadCorrectionTemplates,
} from './correction_templates.js';
import {
  configureTextModal,
} from './text_modal.js';
import { bindChatEvents } from './app_chat_events.js';
import { bindLayoutEvents } from './app_layout_events.js';
import { bindModelOutputEvents } from './app_model_output_events.js';
import { bindSessionRunEvents } from './app_session_run_events.js';
import { startRuntimeHealthPolling } from './runtime_health_monitor.js';

export function configureApp(context) {
  const { elements } = context;
  configureTextModal({
    setStatus: context.setStatus,
  });
  configureLayout({
    getSessionRecords: context.sessionRecords,
    onChatRailWidthChanged: context.updateUnifiedChatControls,
  });
  configureRuntimeControls({
    getRuntimeHarness: context.runtimeHarness,
    updateCorrectionTemplateDescription: context.updateCorrectionTemplateDescription,
    updateRetryRunControls: context.updateRetryRunControls,
    updateRuntimeHarnessBadge: context.updateRuntimeHarnessBadge,
  });
  configureCorrectionTemplates({
    getDefaultTemplateId: context.defaultCorrectionTemplateId,
    onDefaultTemplateId: (templateId) => patchAppConfig({ default_correction_template_id: templateId }),
    onTemplatesChanged: context.updateCorrectionChatControls,
  });
  configureTheme({
    onThemeChanged: () => {
      context.updateArtifactLinks();
      if (context.currentStructuredModel()) {
        context.renderInlineDiagram(context.currentStructuredModel(), {
          forceRender: true,
          preserveViewport: true,
        });
      }
    },
  });
}

export async function bootApp(context) {
  initTheme();
  context.applyModelToolbarIcons();
  restoreDiagramWorkspaceHeight();
  restoreAppRailLayout();
  await loadConfig();
  startRuntimeHealthPolling();
  await loadCorrectionTemplates();
  await loadHarnesses();
  triggerStartupProviderModelRefreshes();
  await context.loadSessions();
  const sessions = context.sessionRecords();
  if (sessions.length) {
    await context.loadSession(sessions[0].session_id);
  } else {
    context.updateSessionWorkspace();
  }
  await context.loadRuns();
  context.updateCorrectionChatControls();
  context.updateQuestionChatControls();
  context.updateUnifiedChatControls();
}

export function bindAppEvents(context) {
  bindLayoutEvents(context);
  bindSessionRunEvents(context);
  bindChatEvents(context);
  bindModelOutputEvents(context);
}

export function startApp(context) {
  const body = document.body;
  body?.classList.add("app-booting");
  body?.setAttribute("aria-busy", "true");
  const finishBoot = () => {
    body?.classList.remove("app-booting");
    body?.removeAttribute("aria-busy");
  };
  try {
    configureApp(context);
    bindAppEvents(context);
    setupHeaderLayoutObserver();
    scheduleDiagramControlPlacement();
    scheduleHeaderOverflowUpdate();
    setInterval(() => {
      if (context.elements.unifiedChatPanel && !context.elements.unifiedChatPanel.hidden) context.renderModelOutputMarkdown();
      scheduleDiagramControlPlacement();
      scheduleHeaderOverflowUpdate();
    }, 500);
    return bootApp(context).finally(finishBoot);
  } catch (error) {
    finishBoot();
    throw error;
  }
}
