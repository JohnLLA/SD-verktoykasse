// Plass til oppdateringsvarselet. Selve versjonssjekken og varselet bygges i
// steg 4; her finnes bare stedet varselet skal stå, og funksjonen som viser
// det. Grensesnittet gjør ingen nettkall.

import { t } from "../i18n/nb";
import { h, replace } from "../ui/dom";

export interface UpdateNotice {
  el: HTMLElement;
  /** Viser «Det finnes en ny versjon» eller skjuler varselet (`null`). */
  show(version: string | null): void;
}

export function createUpdateNotice(): UpdateNotice {
  const el = h("div", { class: "update-slot", id: "update-slot", hidden: true });
  return {
    el,
    show(version) {
      if (version === null) {
        el.hidden = true;
        replace(el);
        return;
      }
      el.hidden = false;
      replace(
        el,
        h("div", { class: "banner", role: "status" }, h("span", { text: t.update.available(version) }), h("button", { type: "button", class: "btn btn-quiet", text: t.update.dismiss, onclick: () => { el.hidden = true; } })),
      );
    },
  };
}
