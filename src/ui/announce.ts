// Kort beskjed til skjermlesere (aria-live), og en synlig melding nederst.

import { h } from "./dom";

let region: HTMLElement | null = null;
let clearTimer: number | undefined;

export function mountAnnouncer(parent: HTMLElement): void {
  region = h("div", { class: "toast", role: "status", "aria-live": "polite", "aria-atomic": "true" });
  parent.append(region);
}

/** Sier fra til skjermleseren og viser meldingen en stund. */
export function announce(message: string, durationMs = 5000): void {
  if (!region) return;
  region.textContent = message;
  region.classList.add("toast-visible");
  window.clearTimeout(clearTimer);
  clearTimer = window.setTimeout(() => {
    region?.classList.remove("toast-visible");
  }, durationMs);
}
