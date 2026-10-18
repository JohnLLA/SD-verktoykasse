// Framdriftslinje med riktig rolle for skjermlesere.

import { clampPercent } from "../lib/format";
import { h } from "./dom";

export interface ProgressBar {
  el: HTMLElement;
  /** `percent` er null når total er ukjent (stripete, uten tall). */
  set(percent: number | null, text?: string): void;
}

export function progressBar(label: string): ProgressBar {
  const fill = h("div", { class: "bar-fill" });
  const el = h("div", { class: "bar", role: "progressbar", "aria-label": label, "aria-valuemin": 0, "aria-valuemax": 100 }, fill);
  return {
    el,
    set(percent, text) {
      if (percent === null) {
        el.removeAttribute("aria-valuenow");
        el.classList.add("bar-indeterminate");
        fill.style.width = "";
      } else {
        const p = clampPercent(percent);
        el.classList.remove("bar-indeterminate");
        el.setAttribute("aria-valuenow", String(p));
        fill.style.width = `${p}%`;
      }
      if (text) el.setAttribute("aria-valuetext", text);
      else el.removeAttribute("aria-valuetext");
    },
  };
}
