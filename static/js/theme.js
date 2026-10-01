import { els } from "./dom.js";

const THEME_STORAGE_KEY = "cdmapp.theme";

let onThemeChanged = () => {};

export function configureTheme(options = {}) {
  if (typeof options.onThemeChanged === "function") onThemeChanged = options.onThemeChanged;
}

export function isDarkTheme() {
  return document.body.classList.contains("theme-dark");
}

export function applyTheme(theme) {
  const resolved = theme === "light" || theme === "dark" ? theme : "dark";
  document.body.classList.toggle("theme-dark", resolved === "dark");
  localStorage.setItem(THEME_STORAGE_KEY, resolved);
  if (els.themeToggle) {
    els.themeToggle.classList.toggle("is-dark", resolved === "dark");
    els.themeToggle.innerHTML = `
      <span class="theme-toggle-icon theme-toggle-sun" aria-hidden="true">
        <svg viewBox="0 0 24 24" focusable="false"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path></svg>
      </span>
      <span class="theme-toggle-icon theme-toggle-moon" aria-hidden="true">
        <svg viewBox="0 0 24 24" focusable="false"><path d="M20.5 14.5A8 8 0 1 1 9.5 3.5 6.5 6.5 0 0 0 20.5 14.5z"></path></svg>
      </span>`;
    els.themeToggle.setAttribute("aria-label", resolved === "dark" ? "Switch to light theme" : "Switch to dark theme");
    els.themeToggle.setAttribute("aria-pressed", String(resolved === "dark"));
  }
  onThemeChanged(resolved);
}

export function initTheme() {
  const stored = localStorage.getItem(THEME_STORAGE_KEY);
  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(stored || (prefersDark ? "dark" : "light"));
}
