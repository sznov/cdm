const REFRESH_ICON = `
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M4 12a8 8 0 0 1 13.6-5.7"></path>
        <path d="M18 3v5h-5"></path>
        <path d="M20 12a8 8 0 0 1-13.6 5.7"></path>
        <path d="M6 21v-5h5"></path>
      </svg>
    `;

export const TRACE_ICON_SVGS = {
  retry: REFRESH_ICON,
  refresh: REFRESH_ICON,
  input: `
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <rect x="10" y="5" width="10" height="14" rx="2"></rect>
        <path d="M3 12h10"></path>
        <path d="M9 8l4 4-4 4"></path>
      </svg>
    `,
  output: `
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <rect x="4" y="5" width="10" height="14" rx="2"></rect>
        <path d="M11 12h10"></path>
        <path d="M17 8l4 4-4 4"></path>
      </svg>
    `,
  raw: `
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M8 8 4 12l4 4"></path>
        <path d="m16 8 4 4-4 4"></path>
        <path d="m14 5-4 14"></path>
      </svg>
    `,
  log: `
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M8 6h11"></path>
        <path d="M8 12h11"></path>
        <path d="M8 18h11"></path>
        <path d="M4 6h.01"></path>
        <path d="M4 12h.01"></path>
        <path d="M4 18h.01"></path>
      </svg>
    `,
};
