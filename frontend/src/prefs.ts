// Per-browser display preferences (Phase 18). localStorage, unlike the session: they should outlive the tab.
// Every access is guarded, because storage can be blocked (private mode, strict settings).

export type Theme = "system" | "light" | "dark";
export type DeviceView = "list" | "grid";

const THEME_KEY = "smartiot.theme";
const VIEW_KEY = "smartiot.view";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // blocked: the choice lasts until the page is reloaded
  }
}

export function loadTheme(): Theme {
  const value = read(THEME_KEY);
  return value === "light" || value === "dark" ? value : "system";
}

/** Apply the theme to <html data-theme>; "system" removes it so the OS setting decides (styles.css). */
export function applyTheme(theme: Theme): void {
  if (theme === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
  write(THEME_KEY, theme);
}

export function loadView(): DeviceView {
  return read(VIEW_KEY) === "grid" ? "grid" : "list";
}

export function saveView(view: DeviceView): void {
  write(VIEW_KEY, view);
}
