export function formatNumber(value: number | null | undefined, unit: string, digits = 1): string {
  return value == null ? "—" : `${value.toFixed(digits)} ${unit}`;
}

export function formatRelative(iso: string | null, now: number): string {
  if (!iso) return "never";
  const seconds = Math.max(0, Math.round((now - Date.parse(iso)) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}
