// Skjermen for et verktøy som ikke er lastet ned: hva det gjør, størrelse,
// «Last ned verktøyet», framdrift og feil. Bygget som modellnedlastingen i
// Transkribering (`docs/skjermbilder/04-nedlasting-*` og `18-nedlasting-feil-*`).

import { t } from "../../i18n/nb";
import { formatBytes, formatPercent } from "../../lib/format";
import { h, replace } from "../../ui/dom";
import { icon } from "../../ui/icons";
import { progressBar, type ProgressBar } from "../../ui/progress";
import type { JvToolId } from "./api";
import type { JvController } from "./controller";
import { jvErrorText } from "./errors";
import type { ToolTexts } from "./texts";

export interface InstallView {
  el: HTMLElement;
  update(): void;
  updateProgress(): void;
}

export function createInstallView(c: JvController, id: JvToolId, texts: ToolTexts): InstallView {
  const I = t.jv.install;
  const body = h("div", { class: "install-body" });
  const el = h(
    "div",
    { class: "view-install" },
    h("p", { class: "tool-lead", text: texts.description }),
    body,
    h("p", { class: "info install-local", text: t.jv.common.localNote }),
  );

  let key = "";
  let bar: ProgressBar | null = null;
  let barText: HTMLElement | null = null;

  const facts = (): HTMLElement => {
    const entry = c.toolView(id)?.entry;
    return h(
      "dl",
      { class: "facts" },
      h("div", {}, h("dt", { text: I.accepts }), h("dd", { text: texts.formats })),
      entry && h("div", {}, h("dt", { text: I.size }), h("dd", { text: formatBytes(entry.bytes) })),
      entry && h("div", {}, h("dt", { text: I.version }), h("dd", { text: entry.version })),
    );
  };

  function build(): void {
    bar = null;
    barText = null;
    const screen = c.installScreen(id);
    const st = c.installState(id);
    const view = c.toolView(id);

    if (screen === "soon") {
      replace(
        body,
        facts(),
        h(
          "div",
          { class: "card card-soon", role: "status" },
          icon("info", 24),
          h("div", { class: "card-body" }, h("p", { class: "card-title", text: I.comingTitle(c.catalogPlatform()) }), h("p", { class: "card-sub", text: I.comingHint })),
        ),
      );
      return;
    }

    if (screen === "needs_os" || screen === "needs_app") {
      const title = screen === "needs_os" ? I.needsOsTitle(view?.entry?.min_os ?? "") : I.needsAppTitle;
      const hint = screen === "needs_os" ? I.needsOsHint : I.needsAppHint;
      replace(
        body,
        facts(),
        h(
          "div",
          { class: "card card-error", role: "alert" },
          icon("alert", 24),
          h("div", { class: "card-body" }, h("p", { class: "card-title", text: title }), h("p", { text: hint })),
        ),
      );
      return;
    }

    if (screen === "checking") {
      const checkBar = progressBar(I.checking);
      checkBar.set(null);
      replace(body, facts(), h("div", { class: "card", role: "status" }, icon("download", 24), h("div", { class: "card-body" }, h("p", { class: "card-title", text: I.checking }), checkBar.el)));
      return;
    }

    if (screen === "no_catalog") {
      const err = jvErrorText(c.catalogError ?? { code: "catalog_missing" });
      replace(
        body,
        facts(),
        h(
          "div",
          { class: "card card-error", role: "alert" },
          icon("alert", 24),
          h(
            "div",
            { class: "card-body" },
            h("p", { class: "card-title", text: I.catalogFailedTitle }),
            h("p", { class: "card-strong", text: err.title }),
            h("p", { text: err.hint }),
            h("button", { type: "button", class: "btn", text: t.common.retry, onclick: () => void c.loadCatalog(true) }),
          ),
        ),
      );
      return;
    }

    // screen === "ready"
    if (st.status === "starting" || st.status === "downloading" || st.status === "installing") {
      const installing = st.status === "installing";
      bar = progressBar(installing ? I.installing : I.downloading);
      barText = h("p", { class: "card-sub" });
      replace(
        body,
        facts(),
        h(
          "div",
          { class: "card", role: "status" },
          icon("download", 24),
          h(
            "div",
            { class: "card-body" },
            h("p", { class: "card-title", text: installing ? I.installing : I.downloading }),
            bar.el,
            barText,
          ),
          h("button", {
            type: "button",
            class: "btn",
            text: I.cancel,
            disabled: st.cancelRequested || installing,
            onclick: () => c.cancelInstall(id),
          }),
        ),
      );
      return;
    }

    const failed = st.status === "failed" && st.error ? jvErrorText(st.error) : null;
    replace(
      body,
      facts(),
      failed &&
        h(
          "div",
          { class: "card card-error", role: "alert" },
          icon("alert", 24),
          h(
            "div",
            { class: "card-body" },
            h("p", { class: "card-title", text: I.failedTitle }),
            h("p", { class: "card-strong", text: failed.title }),
            h("p", { text: failed.hint }),
          ),
        ),
      st.status === "cancelled" && h("p", { class: "info", role: "status", text: I.cancelled }),
      h(
        "div",
        { class: "card" },
        icon("download", 24),
        h(
          "div",
          { class: "card-body" },
          h("p", { class: "card-title", text: texts.name }),
          h("p", { class: "card-sub", text: I.onlineNote }),
        ),
        h("button", {
          type: "button",
          class: "btn btn-primary btn-large",
          text: failed ? t.common.retry : I.download,
          onclick: () => void c.install(id),
        }),
      ),
    );
  }

  function updateProgress(): void {
    const st = c.installState(id);
    if (!bar || !barText) return;
    if (st.status === "installing" || st.total <= 0) {
      bar.set(null);
      barText.textContent = "";
      return;
    }
    const pct = (st.downloaded / st.total) * 100;
    bar.set(pct, formatPercent(pct));
    barText.textContent = `${I.progress(formatBytes(st.downloaded), formatBytes(st.total))} · ${formatPercent(pct)}`;
  }

  function update(): void {
    const st = c.installState(id);
    const next = [c.installScreen(id), st.status, st.error?.code ?? "", st.cancelRequested, c.toolView(id)?.entry?.version ?? "", c.catalogError?.code ?? ""].join("|");
    if (next !== key) {
      key = next;
      build();
    }
    updateProgress();
  }

  update();
  return { el, update, updateProgress };
}
