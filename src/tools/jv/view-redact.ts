// Sladding, steg 1 «Finn»: treffene i en tabell med type, side, utdrag og
// avkrysning. Forkastede kandidater står i en egen gruppe, merket og avkrysset.
// Brukeren kan bare krysse av og på; ingenting annet i planen kan endres.

import { t } from "../../i18n/nb";
import { h } from "../../ui/dom";
import type { JvToolId, PlanItem } from "./api";
import type { JvController } from "./controller";
import { findSummary } from "./paths";
import { visibleWarnings, warningsBlock } from "./view-result";

const X = t.jv.redact;

export function itemWhere(i: PlanItem): string {
  const place = X.placements[i.placement] ?? "";
  if (i.placement === "side" || place === "") return i.page === null ? "" : X.page(i.page);
  return i.page === null ? place : `${place}, ${X.page(i.page).toLowerCase()}`;
}

export function itemType(i: PlanItem): string {
  return X.types[i.type] ?? i.type;
}

/** Advarselen fra verktøyet om forkastede treff forklares av gruppen under, og sier det motsatte av avkrysningen. */
export function hideRejectedWarning(w: string): boolean {
  return /IKKE merket for sladding/.test(w);
}

export interface RedactView {
  el: HTMLElement;
  update(): void;
}

export function createRedactReview(c: JvController, id: JvToolId): RedactView {
  const body = h("div", { class: "review" });
  const el = h(
    "section",
    { class: "block review-block", "aria-labelledby": "jv-review-title" },
    h("h2", { id: "jv-review-title", class: "block-title", tabindex: -1, text: X.reviewTitle }),
    body,
  );
  let key = "";
  const boxes = new Map<string, HTMLInputElement>();
  const counter = h("p", { class: "help review-count", role: "status", "aria-live": "polite" });

  function table(items: PlanItem[], caption: string): HTMLElement {
    return h(
      "table",
      { class: "plan-table" },
      h("caption", { class: "offscreen", text: caption }),
      h(
        "thead",
        {},
        h(
          "tr",
          {},
          h("th", { scope: "col", text: X.colRedact }),
          h("th", { scope: "col", text: X.colType }),
          h("th", { scope: "col", text: X.colPage }),
          h("th", { scope: "col", text: X.colExcerpt }),
        ),
      ),
      h(
        "tbody",
        {},
        ...items.map((i) => {
          const where = itemWhere(i);
          const box = h("input", {
            type: "checkbox",
            class: "plan-check",
            checked: i.redact,
            "aria-label": X.toggle(itemType(i), where || X.colExcerpt),
            onchange: () => c.setRedact(id, i.id, box.checked),
          });
          boxes.set(i.id, box);
          return h(
            "tr",
            { class: i.rejected ? "plan-row plan-rejected" : "plan-row" },
            h("td", { class: "plan-cell-check" }, box),
            h("td", {}, h("span", { text: itemType(i) }), i.rejected && h("span", { class: "badge badge-warn", text: X.rejectedBadge })),
            h("td", { class: "plan-cell-page", text: where }),
            h("td", { class: "plan-cell-excerpt", text: i.excerpt }),
          );
        }),
      ),
    );
  }

  function build(): void {
    const r = c.session(id).redact;
    boxes.clear();
    const regular = r.items.filter((i) => !i.rejected);
    const rejected = r.items.filter((i) => i.rejected);
    const warnings = warningsBlock(visibleWarnings(r.findReport, hideRejectedWarning));
    const summary = findSummary(r.items);
    const parts: (HTMLElement | null)[] = [
      h("p", { class: "review-summary", text: summary }),
      h("p", { class: "help", text: X.reviewHint }),
      warnings,
      r.items.length === 0 ? h("p", { class: "info", text: X.noHits }) : null,
      r.items.length > 0
        ? h(
            "div",
            { class: "button-row" },
            h("button", { type: "button", class: "btn", text: X.selectAll, onclick: () => c.setRedactAll(id, true) }),
            h("button", { type: "button", class: "btn", text: X.selectNone, onclick: () => c.setRedactAll(id, false) }),
          )
        : null,
      counter,
      regular.length > 0 ? table(regular, X.reviewTitle) : null,
      rejected.length > 0
        ? h(
            "section",
            { class: "rejected-group", "aria-labelledby": "jv-rejected-title" },
            h("h3", { id: "jv-rejected-title", class: "result-subtitle", text: X.rejectedTitle }),
            h("p", { class: "warn", text: X.rejectedHint }),
            table(rejected, X.rejectedTitle),
          )
        : null,
    ];
    body.replaceChildren(...parts.filter((n): n is HTMLElement => n !== null));
  }

  function sync(): void {
    const r = c.session(id).redact;
    for (const i of r.items) {
      const b = boxes.get(i.id);
      if (b) b.checked = i.redact;
    }
    const on = r.items.filter((i) => i.redact).length;
    counter.textContent = r.items.length > 0 ? X.selected(on, r.items.length) : "";
  }

  function update(): void {
    const r = c.session(id).redact;
    const next = [r.step, r.planPath ?? "", r.items.length, r.items[0]?.id ?? ""].join("|");
    if (next !== key) {
      key = next;
      build();
    }
    sync();
  }

  return { el, update };
}
