// Bekreftelsesvindu med det innebygde <dialog>-elementet: tastaturet fanges
// i vinduet, Esc lukker, og fokus går tilbake dit det var.

import { t } from "../i18n/nb";
import { h, nextId } from "./dom";

export interface ConfirmOptions {
  title: string;
  body: string;
  confirmLabel: string;
  cancelLabel?: string;
  /** Ødeleggende handling: bekreftknappen får rød farge og er ikke forvalgt. */
  danger?: boolean;
}

/** Gir `true` hvis brukeren bekrefter. */
export function confirmDialog(opts: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    const previous = document.activeElement as HTMLElement | null;
    const titleId = nextId("dlg-title");
    const bodyId = nextId("dlg-body");
    let result = false;

    const cancel = h("button", {
      type: "button",
      class: "btn",
      text: opts.cancelLabel ?? t.common.cancel,
      onclick: () => dialog.close(),
    });
    const confirm = h("button", {
      type: "button",
      class: opts.danger ? "btn btn-danger" : "btn btn-primary",
      text: opts.confirmLabel,
      onclick: () => {
        result = true;
        dialog.close();
      },
    });
    const dialog = h(
      "dialog",
      { class: "modal", "aria-labelledby": titleId, "aria-describedby": bodyId },
      h("h2", { id: titleId, text: opts.title }),
      h("p", { id: bodyId, text: opts.body }),
      h("div", { class: "modal-actions" }, cancel, confirm),
    );
    dialog.addEventListener("close", () => {
      dialog.remove();
      previous?.focus();
      resolve(result);
    });
    document.body.append(dialog);
    dialog.showModal();
    // Ved ødeleggende handlinger starter fokus på «Avbryt».
    (opts.danger ? cancel : confirm).focus();
  });
}
