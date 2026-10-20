// Ikoner som innebygd SVG (ingen eksterne filer eller fonter). Innholdet er
// faste tekster skrevet her, aldri data fra brukeren.

const PATHS: Record<string, string> = {
  waveform:
    '<path d="M4 10v4M8 6v12M12 3v18M16 8v8M20 11v2" stroke-linecap="round"/>',
  settings:
    '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1" stroke-linecap="round"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5" stroke-linecap="round"/>',
  upload:
    '<path d="M12 16V4M7 9l5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" stroke-linecap="round" stroke-linejoin="round"/>',
  file: '<path d="M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z M14 3v5h5" stroke-linejoin="round"/>',
  play: '<path d="M8 5v14l11-7z" fill="currentColor" stroke="none"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5" stroke-linecap="round" stroke-linejoin="round"/>',
  alert:
    '<path d="M12 3l10 18H2z" stroke-linejoin="round"/><path d="M12 10v5M12 17.5v.5" stroke-linecap="round"/>',
  back: '<path d="M15 5l-7 7 7 7" stroke-linecap="round" stroke-linejoin="round"/>',
  download:
    '<path d="M12 4v12M7 11l5 5 5-5M4 19h16" stroke-linecap="round" stroke-linejoin="round"/>',
  folder:
    '<path d="M3 7a1 1 0 0 1 1-1h5l2 2h8a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z" stroke-linejoin="round"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3" />',
  save: '<path d="M5 4h11l3 3v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z M8 4v5h7V4 M8 20v-6h8v6" stroke-linejoin="round"/>',
  close: '<path d="M6 6l12 12M18 6L6 18" stroke-linecap="round"/>',
  trash:
    '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-12M9 7V4h6v3" stroke-linecap="round" stroke-linejoin="round"/>',
  compare:
    '<path d="M4 5h6v14H4zM14 5h6v14h-6z M6.5 9h1M6.5 12h1M16.5 9h1M16.5 12h1" stroke-linecap="round" stroke-linejoin="round"/>',
  metadata:
    '<path d="M3 12V4h8l9 9-8 8z" stroke-linejoin="round"/><circle cx="7.5" cy="8.5" r="1.2"/>',
  keyframes:
    '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9.5v5l4.5-2.5z" stroke-linejoin="round"/>',
  loudness:
    '<path d="M4 9v6h3.5L12 19V5L7.5 9zM15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11" stroke-linecap="round" stroke-linejoin="round"/>',
  subtitles:
    '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 11h4M13 11h4M7 15h2M11 15h6" stroke-linecap="round"/>',
  table:
    '<rect x="3" y="5" width="18" height="14" rx="1.5"/><path d="M3 10h18M3 14.5h18M9 5v14M15 5v14"/>',
  ocr: '<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M7 12h10" stroke-linecap="round" stroke-linejoin="round"/>',
  redact:
    '<path d="M6 3h8l4 4v14H6z M14 3v4h4" stroke-linejoin="round"/><path d="M9 12h6M9 16h6" stroke-width="3.2" stroke-linecap="butt"/>',
  language:
    '<path d="M4 6h9M8.5 4v2M6 6c.5 3 3 6 6 7M12 6c-.7 3.5-3.5 6.5-7 8M12.5 20l4-9 4 9M13.9 17h5.2" stroke-linecap="round" stroke-linejoin="round"/>',
  swap: '<path d="M7 4 3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7" stroke-linecap="round" stroke-linejoin="round"/>',
};

/** Et ikon som `<span>`, i tekstfargen, skjult for skjermlesere. */
export function icon(name: keyof typeof PATHS | string, size = 20): HTMLSpanElement {
  const span = document.createElement("span");
  span.className = "icon";
  span.setAttribute("aria-hidden", "true");
  const body = PATHS[name] ?? "";
  span.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">${body}</svg>`;
  return span;
}

/** Ikon som markup, til verktøyregisteret (`registry.ts`). */
export const ICONS = PATHS;
