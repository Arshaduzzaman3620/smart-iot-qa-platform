// Inline SVG icons (24x24, stroke = currentColor), so the dashboard needs no icon font or CDN and the
// strict Content-Security-Policy stays as it is. Decorative: hidden from screen readers.

import type { ReactNode } from "react";

function Icon({ children, size = 20 }: { children: ReactNode; size?: number }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}

type P = { size?: number };

export const HomeIcon = (p: P) => (
  <Icon {...p}><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5" /></Icon>
);
export const GridIcon = (p: P) => (
  <Icon {...p}><rect x="3" y="3" width="7" height="7" rx="2" /><rect x="14" y="3" width="7" height="7" rx="2" />
    <rect x="3" y="14" width="7" height="7" rx="2" /><rect x="14" y="14" width="7" height="7" rx="2" /></Icon>
);
export const DevicesIcon = (p: P) => (
  <Icon {...p}><rect x="4" y="4" width="16" height="16" rx="4" /><circle cx="12" cy="12" r="3" />
    <path d="M12 4v2M12 18v2M4 12h2M18 12h2" /></Icon>
);
export const BellIcon = (p: P) => (
  <Icon {...p}><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0" /></Icon>
);
export const ChipIcon = (p: P) => (
  <Icon {...p}><rect x="6" y="6" width="12" height="12" rx="2" /><rect x="9.5" y="9.5" width="5" height="5" rx="1" />
    <path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" /></Icon>
);
export const ThermometerIcon = (p: P) => (
  <Icon {...p}><path d="M14 14.8V5a2 2 0 1 0-4 0v9.8a4 4 0 1 0 4 0Z" /><path d="M12 9v7" /></Icon>
);
export const DropletIcon = (p: P) => (
  <Icon {...p}><path d="M12 3s6 6.4 6 11a6 6 0 0 1-12 0c0-4.6 6-11 6-11Z" /></Icon>
);
export const BatteryIcon = (p: P) => (
  <Icon {...p}><rect x="2" y="7" width="17" height="10" rx="2.5" /><path d="M22 11v2" /><path d="M6 10.5v3M9.5 10.5v3" /></Icon>
);
export const GaugeIcon = (p: P) => (
  <Icon {...p}><path d="M4.9 19a9 9 0 1 1 14.2 0" /><path d="m12 13 4-4" /><circle cx="12" cy="13" r="1.2" /></Icon>
);
export const SunIcon = (p: P) => (
  <Icon {...p}><circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></Icon>
);
export const WifiIcon = (p: P) => (
  <Icon {...p}><path d="M2 8.8a15 15 0 0 1 20 0" /><path d="M5 12.6a10 10 0 0 1 14 0" /><path d="M8.5 16.3a5 5 0 0 1 7 0" />
    <circle cx="12" cy="20" r="0.8" /></Icon>
);
export const LogoutIcon = (p: P) => (
  <Icon {...p}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="m16 17 5-5-5-5" /><path d="M21 12H9" /></Icon>
);
export const CloseIcon = (p: P) => <Icon {...p}><path d="M18 6 6 18M6 6l12 12" /></Icon>;
export const CheckIcon = (p: P) => <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="m8 12 2.8 2.8L16 9.5" /></Icon>;
export const UploadIcon = (p: P) => (
  <Icon {...p}><path d="M12 15V3" /><path d="m7 8 5-5 5 5" /><path d="M20 15v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-4" /></Icon>
);
export const ShieldIcon = (p: P) => (
  <Icon {...p}><path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6l-8-3Z" /><path d="m9 12 2 2 4-4" /></Icon>
);
export const PinIcon = (p: P) => (
  <Icon {...p}><path d="M12 21s7-6.2 7-12a7 7 0 0 0-14 0c0 5.8 7 12 7 12Z" /><circle cx="12" cy="9" r="2.5" /></Icon>
);

/** The SmartIoT mark: a house with a signal wave. */
export function Logo({ size = 32 }: P) {
  return (
    <svg className="logo" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="9" className="logo-bg" />
      <path d="M8 15.5 16 9l8 6.5V23a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1Z" fill="none" stroke="#fff" strokeWidth="2"
            strokeLinejoin="round" />
      <path d="M13 19.2a4.2 4.2 0 0 1 6 0" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
      <circle cx="16" cy="21.6" r="1.2" fill="#fff" />
    </svg>
  );
}
