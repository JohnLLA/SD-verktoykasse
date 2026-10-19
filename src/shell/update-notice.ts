// Plassen øverst i innholdet der oppdateringsvarselet står. Selve sjekken ligger
// i `update-check.ts`; dette er bare visningen. Ingen nettkall her.

import { t } from "../i18n/nb";
import { h, replace } from "../ui/dom";

export interface UpdateNotice {
  el: HTMLElement;
  /** Viser «Det finnes en ny versjon» med «Oppdater nå», eller skjuler varselet (`null`). */
  show(version: string | null, onInstall?: () => void): void;
  /** Viser at nedlasting og installasjon pågår. */
  installing(): void;
  /** Viser at oppdateringen mislyktes, med mulighet til å prøve igjen. */
  failed(onRetry: () => void): void;
}

export function createUpdateNotice(): UpdateNotice {
  const el = h("div", { class: "update-slot", id: "update-slot", hidden: true });
  const hide = () => {
    el.hidden = true;
    replace(el);
  };
  const banner = (...children: (Node | string | null)[]) => {
    el.hidden = false;
    replace(el, h("div", { class: "banner", role: "status" }, ...children));
  };
  return {
    el,
    show(version, onInstall) {
      if (version === null) {
        hide();
        return;
      }
      banner(
        h("span", { text: t.update.available(version) }),
        onInstall ? h("button", { type: "button", class: "btn btn-primary", text: t.update.install, onclick: onInstall }) : null,
        h("button", { type: "button", class: "btn btn-quiet", text: t.update.dismiss, onclick: hide }),
      );
    },
    installing() {
      banner(h("span", { text: t.update.installing }));
    },
    failed(onRetry) {
      banner(
        h("span", { text: t.update.failed }),
        h("button", { type: "button", class: "btn", text: t.common.retry, onclick: onRetry }),
        h("button", { type: "button", class: "btn btn-quiet", text: t.update.dismiss, onclick: hide }),
      );
    },
  };
}
