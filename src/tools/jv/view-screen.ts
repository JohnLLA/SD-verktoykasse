// Skjermen for et verktøy som er lastet ned. Samme oppbygging som
// Transkribering: slippsone, «Valg», handling og resultat.
//
//   Øverst:   slippsone og filene som er lagt til
//   Valg:     feltene fra skjemaet
//   Utmappe:  standard er mappen til første fil
//   Kjør:     framdrift og Avbryt
//   Resultat: summary, advarsler og utfiler
//
// Sladding har to steg (Finn og Sladd) og viser gjennomgangen mellom dem.

import { t } from "../../i18n/nb";
import { fileName } from "../../lib/files";
import { formatPercent } from "../../lib/format";
import type { Platform } from "../../platform/types";
import { h, replace } from "../../ui/dom";
import { icon } from "../../ui/icons";
import { progressBar, type ProgressBar } from "../../ui/progress";
import type { JvToolId } from "./api";
import type { JvController, Session } from "./controller";
import { needsOutDir, type ToolSchema } from "./schema";
import type { ToolTexts } from "./texts";
import { createFields } from "./view-fields";
import { createRedactReview } from "./view-redact";
import { createResult, createRunError } from "./view-result";

const S = t.jv.screen;

export type ScreenMode = "setup" | "running" | "result" | "review";

/** Hva skjermen viser, ut fra økten. Ren funksjon. */
export function screenMode(schema: ToolSchema, s: Session): ScreenMode {
  if (s.run.status === "starting" || s.run.status === "running") return "running";
  if (s.run.status === "done" && s.run.kind === "run") return "result";
  if (schema.twoStep && s.redact.step === "review") return "review";
  return "setup";
}

export interface ToolScreen {
  el: HTMLElement;
  update(): void;
  updateProgress(): void;
  setDragging(over: boolean): void;
  focusResult(): void;
}

export function createToolScreen(c: JvController, id: JvToolId, schema: ToolSchema, texts: ToolTexts, platform: Platform): ToolScreen {
  const hasFolders = schema.acceptsFolders === true;
  let dragging = false;

  // ---- slippsone
  const dropTitle = h("p", { class: "drop-title" });
  const chooseButton = h("button", { type: "button", class: "btn btn-primary btn-large", onclick: () => void c.chooseFiles(id, { title: texts.dialogTitle, filterName: texts.filterName }) });
  const folderButton = hasFolders ? h("button", { type: "button", class: "btn btn-large btn-folder", text: S.chooseFolder, onclick: () => void c.chooseFolder(id, texts.dialogTitle) }) : null;
  const drop = h(
    "div",
    {
      class: "dropzone",
      onclick: (e: Event) => {
        if (!(e.target as HTMLElement).closest("button")) void c.chooseFiles(id, { title: texts.dialogTitle, filterName: texts.filterName });
      },
    },
    icon("upload", 40),
    dropTitle,
    h("p", { class: "drop-or", text: S.or }),
    h("div", { class: "drop-buttons" }, chooseButton, folderButton),
    h("p", { class: "drop-formats", text: texts.formats }),
  );

  const notice = h("div", { class: "notice", hidden: true });
  const readyList = h("ul", { class: "ready-list" });
  const readySection = h("section", { class: "block", "aria-labelledby": `jv-ready-${id}` }, h("h2", { id: `jv-ready-${id}`, class: "block-title", text: S.readyTitle }), readyList);

  const fields = createFields(c, id, schema);
  const review = schema.twoStep ? createRedactReview(c, id) : null;

  // ---- utmappe
  const outPath = h("p", { class: "path out-path" });
  const outSection = h(
    "section",
    { class: "block out-block", "aria-labelledby": `jv-out-${id}` },
    h("h2", { id: `jv-out-${id}`, class: "block-title", text: S.outTitle }),
    outPath,
    h("div", { class: "button-row" }, h("button", { type: "button", class: "btn", text: S.outChange, onclick: () => void c.chooseOutDir(id, S.outDialogTitle) })),
    h("p", { class: "help", text: t.jv.common.original }),
  );

  const action = h("div", { class: "action" });
  const stage = h("div", { class: "jv-result-slot" });
  let actionKey = "";
  let bar: ProgressBar | null = null;
  let barText: HTMLElement | null = null;
  let resultKey = "";
  let resultHeading: HTMLElement | null = null;

  const el = h("div", { class: "view-new view-jv" }, notice, drop, readySection, fields.el, review?.el, outSection, stage, action);

  // ---- tegning

  function renderDrop(mode: ScreenMode): void {
    const s = c.session(id);
    const compact = s.files.length > 0;
    drop.hidden = mode !== "setup";
    drop.classList.toggle("dropzone-compact", compact);
    drop.classList.toggle("dropzone-over", dragging);
    dropTitle.textContent = dragging ? S.dragging : compact ? S.chooseMore : texts.dropTitle;
    chooseButton.textContent = S.chooseFiles;
  }

  function renderNotice(mode: ScreenMode): void {
    const n = c.session(id).notice;
    notice.hidden = !n || mode !== "setup";
    if (!n) return;
    if (n.kind === "unsupported") {
      replace(
        notice,
        h(
          "div",
          { class: "card card-error", role: "alert" },
          icon("alert", 24),
          h("div", { class: "card-body" }, h("p", { class: "card-title", text: S.unsupportedTitle }), h("p", { text: S.unsupportedHint(n.names, texts.formats) })),
        ),
      );
    } else {
      replace(
        notice,
        h("div", { class: "card card-error", role: "alert" }, icon("alert", 24), h("div", { class: "card-body" }, h("p", { class: "card-title", text: S.needExactly(n.n) }))),
      );
    }
  }

  function renderReady(mode: ScreenMode): void {
    const s = c.session(id);
    readySection.hidden = s.files.length === 0 || mode === "result";
    const readOnly = mode !== "setup";
    const roles = schema.exactFiles === 2 ? S.roles : null;
    replace(
      readyList,
      ...s.files.map((path, i) => {
        const name = fileName(path);
        return h(
          "li",
          { class: "ready-item" },
          icon("file", 20),
          roles && h("span", { class: "badge", text: roles[i] ?? "" }),
          h("span", { class: "ready-name", text: name }),
          !readOnly && roles && i === 0 && s.files.length === 2
            ? h("button", { type: "button", class: "btn btn-icon", "aria-label": S.swap, title: S.swap, onclick: () => c.swapFiles(id) }, icon("swap", 18))
            : null,
          !readOnly
            ? h("button", { type: "button", class: "btn btn-icon", "aria-label": S.removeFile(name), title: t.common.remove, onclick: () => c.removeFile(id, i) }, icon("close", 18))
            : null,
        );
      }),
    );
  }

  function renderOut(mode: ScreenMode): void {
    const s = c.session(id);
    outSection.hidden = mode !== "setup" || !needsOutDir(schema, s.values) || s.files.length === 0;
    outPath.textContent = s.outDir ?? S.outNone;
  }

  function renderAction(mode: ScreenMode): void {
    const s = c.session(id);
    const key = [mode, s.run.status, s.run.cancelRequested, s.run.error?.code ?? "", c.canRun(id), s.files.length, s.redact.loading, s.redact.error?.code ?? "", s.redact.items.length].join("|");
    if (key === actionKey) {
      updateProgress();
      return;
    }
    actionKey = key;
    bar = null;
    barText = null;
    action.hidden = false;

    if (mode === "running") {
      const cancelling = s.run.cancelRequested;
      bar = progressBar(S.progressLabel);
      barText = h("p", { class: "card-sub" });
      replace(
        action,
        h(
          "div",
          { class: "card card-progress", role: "status" },
          icon("file", 24),
          h("div", { class: "card-body" }, h("p", { class: "card-title", text: cancelling ? S.cancelling : s.run.status === "starting" ? S.starting : S.running }), bar.el, barText, h("p", { class: "card-sub", text: S.keepOpen })),
          h("button", { type: "button", class: "btn", text: S.cancel, disabled: cancelling, onclick: () => c.cancelRun(id) }),
        ),
      );
      updateProgress();
      return;
    }

    if (mode === "result") {
      replace(
        action,
        h(
          "div",
          { class: "button-row" },
          schema.twoStep
            ? h("button", { type: "button", class: "btn", text: t.jv.redact.backToReview, onclick: () => c.again(id) })
            : h("button", { type: "button", class: "btn", text: t.jv.result.again, onclick: () => c.again(id) }),
          h("button", { type: "button", class: "btn btn-primary", text: t.jv.result.newJob, onclick: () => c.newJob(id) }),
        ),
      );
      return;
    }

    const err = s.run.status === "failed" && s.run.error ? createRunError(s.run) : null;
    const cancelled = s.run.status === "cancelled" ? h("p", { class: "info", role: "status", text: `${t.jv.result.cancelledTitle}. ${t.jv.result.cancelledHint}` }) : null;

    if (mode === "review") {
      const planError = s.redact.error ? createRunError({ ...s.run, status: "failed", error: s.redact.error, message: null }) : null;
      replace(
        action,
        err,
        planError,
        cancelled,
        h(
          "div",
          { class: "button-row" },
          h("button", { type: "button", class: "btn", text: t.jv.redact.back, onclick: () => c.backToFind(id) }),
          h("button", { type: "button", class: "btn btn-primary btn-large btn-start", text: t.jv.redact.redactButton, disabled: s.redact.loading, onclick: () => void c.redact(id) }),
        ),
      );
      return;
    }

    if (s.files.length === 0) {
      action.hidden = !err && !cancelled;
      replace(action, err, cancelled);
      return;
    }
    replace(
      action,
      err,
      cancelled,
      h("button", {
        type: "button",
        class: "btn btn-primary btn-large btn-start",
        text: schema.twoStep ? t.jv.redact.find : S.run,
        disabled: !c.canRun(id),
        onclick: () => void c.run(id),
      }),
    );
  }

  function updateProgress(): void {
    const s = c.session(id);
    if (!bar || !barText) return;
    if (s.run.status === "running" && s.run.progress > 0) {
      const pct = s.run.progress * 100;
      bar.set(pct, formatPercent(pct));
      barText.textContent = formatPercent(pct);
    } else {
      bar.set(null);
      barText.textContent = "";
    }
  }

  function renderResult(mode: ScreenMode): void {
    const s = c.session(id);
    stage.hidden = mode !== "result";
    if (mode !== "result") {
      resultKey = "";
      resultHeading = null;
      return;
    }
    const key = `${s.run.lastJobId}|${s.run.report ? "r" : ""}`;
    if (key === resultKey) return;
    resultKey = key;
    const planPath = s.redact.planPath;
    const result = createResult(s.run, { platform, draft: schema.draftNotice === true, hidePaths: planPath ? [planPath] : [] });
    resultHeading = result.querySelector("h2");
    replace(stage, result);
  }

  function update(): void {
    const s = c.session(id);
    const mode = screenMode(schema, s);
    el.dataset.mode = mode;
    renderDrop(mode);
    renderNotice(mode);
    renderReady(mode);
    fields.el.hidden = mode !== "setup";
    if (mode === "setup") fields.update();
    if (review) {
      review.el.hidden = mode !== "review";
      if (mode === "review") review.update();
    }
    renderOut(mode);
    renderResult(mode);
    renderAction(mode);
  }

  update();
  return {
    el,
    update,
    updateProgress,
    setDragging(over) {
      dragging = over;
      renderDrop(screenMode(schema, c.session(id)));
    },
    focusResult() {
      resultHeading?.focus();
    },
  };
}
