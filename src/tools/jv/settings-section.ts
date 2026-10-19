// Innstillinger → Verktøy: lista over nedlastede verktøy med versjon og plass,
// og knappene «Se etter oppdateringer», «Oppdater» og «Fjern». Samme oppsett
// som lista over modeller. En oppdatering lastes aldri ned uten at brukeren
// trykker.

import { t } from "../../i18n/nb";
import { formatBytes, formatPercent } from "../../lib/format";
import { announce } from "../../ui/announce";
import { h, replace } from "../../ui/dom";
import { confirmDialog } from "../../ui/modal";
import { isJvToolId, type InstalledView, type JvToolId } from "./api";
import type { JvController } from "./controller";
import { jvErrorText } from "./errors";

const S = t.jv.settings;

export function mountJvSettings(root: HTMLElement, c: JvController): { refresh(): void } {
  const total = h("p", { class: "help" });
  const list = h("ul", { class: "rows" });
  const error = h("div", { class: "card card-error", role: "alert", hidden: true });
  const status = h("p", { class: "help check-now-status", role: "status", "aria-live": "polite" });
  const checkButton = h("button", {
    type: "button",
    class: "btn",
    text: S.checkUpdates,
    onclick: () => {
      checkButton.disabled = true;
      status.textContent = S.checking;
      void c.checkUpdates().then((r) => {
        status.textContent = !r.ok ? S.checkFailed : r.updates === 0 ? S.upToDate : S.foundUpdates(r.updates);
        checkButton.disabled = false;
      });
    },
  });

  const section = h(
    "section",
    { class: "block", "aria-labelledby": "set-jv" },
    h("h2", { id: "set-jv", class: "block-title", text: S.title }),
    h("p", { class: "help", text: S.intro }),
    h("div", { class: "check-now" }, checkButton, status),
    h("p", { class: "help", text: S.onlineNote }),
    error,
    total,
    list,
  );
  root.append(section);

  function showError(e: Parameters<typeof jvErrorText>[0] | null): void {
    error.hidden = e === null;
    if (!e) return;
    const text = jvErrorText(e);
    replace(error, h("div", {}, h("p", { class: "card-strong", text: text.title }), text.hint && h("p", { text: text.hint })));
  }

  function row(i: InstalledView): HTMLElement {
    const view = c.toolView(i.id);
    const id = isJvToolId(i.id) ? i.id : null;
    const st = id ? c.installState(id) : null;
    const updating = id !== null && c.installActive(id);
    const newVersion = view?.update_available ? view.entry?.version : undefined;
    const pct = st && st.total > 0 ? (st.downloaded / st.total) * 100 : null;
    return h(
      "li",
      { class: "row" },
      h(
        "div",
        { class: "row-body" },
        h("p", { class: "row-name", text: i.name }),
        h("p", { class: "row-status", text: S.versionAndSize(i.version, formatBytes(i.bytes)) }),
        updating
          ? h("p", { class: "row-hint", text: pct === null || st?.status === "installing" ? S.updating : `${S.updating} ${formatPercent(pct)}` })
          : newVersion
            ? h("p", { class: "row-hint row-update", text: S.updateAvailable(newVersion) })
            : null,
      ),
      h(
        "div",
        { class: "row-actions" },
        newVersion && !updating && id
          ? h("button", { type: "button", class: "btn", text: S.update, "aria-label": S.updateFile(i.name, newVersion), onclick: () => void c.install(id) })
          : null,
        h("button", {
          type: "button",
          class: "btn btn-danger-quiet",
          text: S.remove,
          "aria-label": S.removeFile(i.name),
          disabled: updating,
          onclick: () => id && void remove(i, id),
        }),
      ),
    );
  }

  async function remove(i: InstalledView, id: JvToolId): Promise<void> {
    const ok = await confirmDialog({
      title: S.confirmTitle,
      body: S.confirmBody(i.name, formatBytes(i.bytes)),
      confirmLabel: S.confirmRemove,
      danger: true,
    });
    if (!ok) return;
    const err = await c.remove(id);
    if (err) showError(err.code === "busy" ? { code: "busy" } : err);
    else announce(S.removed(i.name));
  }

  function render(): void {
    const items = c.installed;
    const used = items.reduce((sum, i) => sum + i.bytes, 0);
    total.textContent = items.length === 0 ? "" : S.total(formatBytes(used));
    if (items.length === 0) replace(list, h("li", { class: "empty", text: S.empty }));
    else replace(list, ...items.map(row));
  }

  c.subscribe((ch) => {
    if (ch.type === "installed" || ch.type === "catalog" || ch.type === "install" || ch.type === "install-progress") render();
  });
  render();

  return {
    refresh() {
      showError(null);
      void c.refreshInstalled();
    },
  };
}
