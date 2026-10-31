import { useState } from "react";

import { applyTheme, loadTheme, type Theme } from "../prefs";
import { MonitorIcon, MoonIcon, SunIcon } from "./Icons";

const OPTIONS: { value: Theme; label: string; icon: JSX.Element }[] = [
  { value: "light", label: "Light", icon: <SunIcon size={16} /> },
  { value: "dark", label: "Dark", icon: <MoonIcon size={16} /> },
  { value: "system", label: "System", icon: <MonitorIcon size={16} /> },
];

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(loadTheme);

  function choose(next: Theme) {
    applyTheme(next);
    setTheme(next);
  }

  return (
    <div className="segmented theme-toggle" role="radiogroup" aria-label="Theme">
      {OPTIONS.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={theme === o.value} title={o.label}
                className={theme === o.value ? "on" : undefined} onClick={() => choose(o.value)}
                data-testid={`theme-${o.value}`}>
          {o.icon}<span className="sr-only">{o.label}</span>
        </button>
      ))}
    </div>
  );
}
