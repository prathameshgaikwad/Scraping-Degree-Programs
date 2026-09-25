// Inline SVG icons, ported 1:1 from the original artifact's ICONS map and markup.

export function Brand({ size = 26 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="12" cy="12" r="3.4" fill="currentColor" />
    </svg>
  );
}

export function User({ size = 15 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="8" r="4" fill="none" stroke="currentColor" strokeWidth="1.75" />
      <path d="M5 20c1.4-3.2 4-4.8 7-4.8s5.6 1.6 7 4.8" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  );
}

export function Star({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3.2l2.6 5.4 5.9.9-4.3 4.2 1 5.9-5.2-2.8-5.2 2.8 1-5.9L3.5 9.5l5.9-.9z" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinejoin="round" />
    </svg>
  );
}

export function Pin({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 21s-6.5-5.6-6.5-10.4a6.5 6.5 0 1 1 13 0C18.5 15.4 12 21 12 21z" fill="none" stroke="currentColor" strokeWidth="1.75" />
      <circle cx="12" cy="10.5" r="2.3" fill="none" stroke="currentColor" strokeWidth="1.75" />
    </svg>
  );
}

export function Clock({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" strokeWidth="1.75" />
      <path d="M12 7.5V12l3 2" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  );
}

export function Grad({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M2 9l10-5 10 5-10 5L2 9z" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinejoin="round" />
      <path d="M6 11.5V16c0 1.4 2.7 2.8 6 2.8s6-1.4 6-2.8v-4.5" fill="none" stroke="currentColor" strokeWidth="1.75" />
    </svg>
  );
}

export function Globe({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" strokeWidth="1.75" />
      <path d="M3.5 12h17M12 3.5c2.2 2.2 3.3 5.2 3.3 8.5S14.2 18.3 12 20.5c-2.2-2.2-3.3-5.2-3.3-8.5S9.8 5.7 12 3.5z" fill="none" stroke="currentColor" strokeWidth="1.75" />
    </svg>
  );
}

export function Check({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M20 6L9 17l-5-5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ToastCheck({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M20 6L9 17l-5-5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Chev({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Search({ size = 17 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="1.9" />
      <path d="M16.5 16.5L21 21" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  );
}

export function Close({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function ResetX({ size = 15 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 4l16 16M20 4L4 20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function Compare({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6 4v14M18 6v12" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
      <path d="M3 18h18" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  );
}

export function SortIcon() {
  return (
    <svg className="sort-ico" width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
      <path className="chev-up" d="M7 14l5-5 5 5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      <path className="chev-dn" d="M7 10l5 5 5-5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
