// Skjermen «Klargjør for Datawrapper». Bygges én gang og oppdateres på stedet,
// så tastaturfokus ikke hopper når brukeren krysser av eller bytter ark.
//
//   Tom:        slippsone og filvelger
//   Leser:      filen analyseres
//   Klar:       valg, knapper, advarsler, forhåndsvisning, tittel og kilde
//   Feilet:     norsk feilmelding og «Velg annen fil»
//
// All tekst står i `src/i18n/nb.ts` (t.jv.datawrapper). Ingen innhold fra
// filen skrives noe annet sted enn til skjermen (regel 2).

import { t } from "../../i18n/nb";
import type { Platform } from "../../platform/types";
import { h, nextId, replace } from "../../ui/dom";
import { icon } from "../../ui/icons";
import type { JvToolId } from "../jv/api";
import type { JvController } from "../jv/controller";
import type { ToolSchema } from "../jv/schema";
import type { ToolTexts } from "../jv/texts";
import type { ToolScreen } from "../jv/view-screen";
import { createRunError, visibleWarnings, warningsBlock } from "../jv/view-result";
import { DatawrapperController, type CopyKey } from "./controller";
import { previewOf, type MadeTable } from "./report";

const D = t.jv.datawrapper;
const S = t.jv.screen;

interface FieldRow {
  key: CopyKey;
  label: string;
  el: HTMLElement;
  input: HTMLInputElement | HTMLTextAreaElement;
  button: HTMLButtonElement;
  /** Skjules når filen ikke har noe å gi (beskrivelse og noter). */
  optional: boolean;
}

export function createDatawrapperScreen(c: JvController, id: JvToolId, _schema: ToolSchema, texts: ToolTexts, platform: Platform): ToolScreen {
  const dw = new DatawrapperController(c, platform);
  let dragging = false;

  // ---- tom: slippsone
  const dropTitle = h("p", { class: "drop-title", text: texts.dropTitle });
  const chooseButton = h("button", { type: "button", class: "btn btn-primary btn-large", text: S.chooseFiles, onclick: () => void dw.chooseFile() });
  const drop = h(
    "div",
    {
      class: "dropzone",
      onclick: (e: Event) => {
        if (!(e.target as HTMLElement).closest("button")) void dw.chooseFile();
      },
    },
    icon("upload", 40),
    dropTitle,
    h("p", { class: "drop-or", text: S.or }),
    h("div", { class: "drop-buttons" }, chooseButton),
    h("p", { class: "drop-formats", text: texts.formats }),
  );

  const notice = h("div", { class: "notice", hidden: true });

  // ---- filen
  const fileName = h("span", { class: "ready-name" });
  const otherFileButton = h("button", { type: "button", class: "btn", text: D.chooseOther, onclick: () => void dw.chooseFile() });
  const fileHeading = h("h2", { id: `jv-ready-${id}`, class: "block-title", tabindex: -1, text: D.fileTitle });
  const fileSection = h(
    "section",
    { class: "block", "aria-labelledby": `jv-ready-${id}` },
    fileHeading,
    h(
      "ul",
      { class: "ready-list" },
      h("li", { class: "ready-item" }, icon("file", 20), fileName, otherFileButton),
    ),
  );

  // ---- leser / feilet
  const reading = h("div", { class: "card card-progress", role: "status" }, icon("file", 24), h("div", { class: "card-body" }, h("p", { class: "card-title", text: D.reading })));
  const failed = h("div", { class: "dw-failed" });

  // ---- valg
  const sheetId = nextId("dw-sheet");
  const sheetSelect = h("select", { class: "input", id: sheetId, onchange: () => dw.setSheet(sheetSelect.value) });
  const sheetRow = h("div", { class: "choice" }, h("label", { class: "field-label", for: sheetId, text: D.sheet }), sheetSelect);
  const tableId = nextId("dw-table");
  const tableSelect = h("select", { class: "input", id: tableId, onchange: () => dw.setTable(Number(tableSelect.value)) });
  const tableRow = h("div", { class: "choice" }, h("label", { class: "field-label", for: tableId, text: D.table }), tableSelect);

  function toggle(label: string, help: string, onChange: (on: boolean) => void): { el: HTMLElement; input: HTMLInputElement } {
    const inputId = nextId("dw-toggle");
    const helpId = nextId("dw-help");
    const input = h("input", { type: "checkbox", role: "switch", class: "switch", id: inputId, "aria-describedby": helpId, onchange: () => onChange(input.checked) });
    return {
      input,
      el: h("div", { class: "choice choice-toggle" }, h("div", { class: "switch-row" }, input, h("label", { for: inputId, text: label })), h("p", { class: "help", id: helpId, text: help })),
    };
  }
  const sums = toggle(D.withSums, D.withSumsHelp, (on) => dw.setWithSums(on));
  const transpose = toggle(D.transpose, D.transposeHelp, (on) => dw.setTranspose(on));

  const removeHint = h("p", { class: "help", id: "dw-remove-hint", text: D.removeHint });
  const removedList = h("ul", { class: "dw-removed-list" });
  const removedTitle = h("h3", { class: "result-subtitle", text: D.removedTitle });
  const restoreAll = h("button", { type: "button", class: "btn btn-quiet", text: D.restoreAll, onclick: () => dw.restoreAllColumns() });
  const removedBlock = h("div", { class: "dw-removed" }, removedTitle, removedList, restoreAll);

  const choices = h(
    "section",
    { class: "block choices", "aria-labelledby": `jv-choices-${id}` },
    h("h2", { id: `jv-choices-${id}`, class: "block-title", text: D.choicesTitle }),
    h("div", { class: "choice-grid" }, sheetRow, tableRow, sums.el, transpose.el),
    removeHint,
    removedBlock,
  );

  // ---- knapper
  const copyButton = h("button", { type: "button", class: "btn btn-primary btn-large", onclick: () => void dw.copyTable() }, icon("copy", 22), h("span", { text: D.copyTable }));
  const saveButton = h("button", { type: "button", class: "btn btn-large", onclick: () => void dw.saveCsv() }, icon("save", 22), h("span", { text: D.saveCsv }));
  const status = h("p", { class: "dw-status", role: "status", "aria-live": "polite" });
  const revealButton = h("button", {
    type: "button",
    class: "btn btn-quiet",
    text: D.reveal,
    onclick: () => {
      if (dw.savedPath) void platform.reveal(dw.savedPath).catch(() => undefined);
    },
  });
  const actions = h("section", { class: "block dw-actions", "aria-label": D.resultTitle }, h("div", { class: "button-row" }, copyButton, saveButton), h("div", { class: "dw-status-row" }, status, revealButton));
  const problem = h("div", { class: "dw-problem" });
  const warnings = h("div", { class: "dw-warnings" });

  // ---- forhåndsvisning
  const previewCount = h("p", { class: "help dw-count" });
  const previewWrap = h("div", { class: "dw-preview-wrap", tabindex: 0, role: "region", "aria-label": D.previewCaption });
  const preview = h(
    "section",
    { class: "block", "aria-labelledby": "dw-preview-title" },
    h("h2", { id: "dw-preview-title", class: "block-title", text: D.previewTitle }),
    previewCount,
    previewWrap,
  );

  // ---- tittel og kilde
  const fieldRows: FieldRow[] = [
    fieldRow("title", D.title, false, false),
    fieldRow("description", D.description, true, true),
    fieldRow("source", D.source, false, false),
    fieldRow("notes", D.notes, true, true),
  ];
  const fieldsSection = h(
    "section",
    { class: "block", "aria-labelledby": "dw-fields-title" },
    h("h2", { id: "dw-fields-title", class: "block-title", text: D.fieldsTitle }),
    h("p", { class: "help", text: D.fieldsHint }),
    h("div", { class: "dw-fields" }, ...fieldRows.map((f) => f.el)),
  );

  function fieldRow(key: CopyKey, label: string, multiline: boolean, optional: boolean): FieldRow {
    const inputId = nextId("dw-field");
    const input = multiline
      ? h("textarea", { class: "input dw-textarea", id: inputId, readonly: true, rows: 2 })
      : h("input", { class: "input", id: inputId, type: "text", readonly: true });
    const button = h("button", {
      type: "button",
      class: "btn dw-copy",
      "aria-label": D.copyField(label),
      onclick: () => void dw.copy(key, value(key)),
    });
    return {
      key,
      label,
      optional,
      input,
      button,
      el: h("div", { class: "dw-field" }, h("label", { class: "field-label", for: inputId, text: label }), h("div", { class: "dw-field-row" }, input, button)),
    };
  }

  function value(key: CopyKey): string {
    const m = dw.made;
    if (!m) return "";
    switch (key) {
      case "title":
        return m.title;
      case "description":
        return m.description;
      case "source":
        return m.source;
      case "notes":
        return m.notes.join("\n");
      default:
        return m.tsv;
    }
  }

  const readyBlocks = [choices, actions, problem, warnings, preview, fieldsSection];
  const el = h("div", { class: "view-new view-jv view-datawrapper" }, notice, drop, fileSection, reading, failed, ...readyBlocks);

  // ---- tegning

  let analysisKey: unknown = null;
  let tableKey = "";
  let madeKey: MadeTable | null = null;
  let lastPhase = dw.phase;
  let pendingFocus: (() => void) | null = null;

  function renderNotice(): void {
    const n = c.session(id).notice;
    notice.hidden = !n;
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
      replace(notice, h("div", { class: "card card-error", role: "alert" }, icon("alert", 24), h("div", { class: "card-body" }, h("p", { class: "card-title", text: S.needExactly(n.n) }))));
    }
  }

  function renderChoices(): void {
    const a = dw.analysis;
    if (a !== analysisKey) {
      analysisKey = a;
      const sheets = dw.sheets();
      replace(sheetSelect, ...sheets.map((s) => h("option", { value: s.name, text: D.sheetOption(s.name, s.suggested) })));
    }
    const sheets = dw.sheets();
    sheetRow.hidden = sheets.length < 2;
    sheetSelect.value = dw.choices.sheet ?? "";
    const tables = dw.tables();
    tableRow.hidden = tables.length < 2;
    // Tabellene byttes når arket byttes. Listen tegnes bare på nytt da, så en åpen liste blir stående.
    const tKey = `${dw.choices.sheet}|${tables.map((x) => `${x.index}:${x.range}`).join(",")}`;
    if (tKey !== tableKey) {
      tableKey = tKey;
      replace(tableSelect, ...tables.map((x) => h("option", { value: String(x.index), text: D.tableOption(x.index, x.range, x.rows, x.suggested) })));
    }
    tableSelect.value = String(dw.choices.table ?? "");
    sums.input.checked = dw.choices.withSums;
    transpose.input.checked = dw.choices.transpose;

    const removed = dw.choices.removed.map((i) => dw.made?.columns.find((col) => col.index === i)).filter((col) => col !== undefined);
    removedBlock.hidden = removed.length === 0;
    replace(
      removedList,
      ...removed.map((col) =>
        h(
          "li",
          { class: "dw-removed-item" },
          h("button", {
            type: "button",
            class: "btn dw-chip",
            "aria-label": D.restoreColumn(col.name || D.emptyHeader),
            title: D.restoreColumn(col.name || D.emptyHeader),
            onclick: () => {
              pendingFocus = () => (previewWrap.querySelector<HTMLElement>("th button") ?? previewWrap).focus();
              dw.restoreColumn(col.index);
            },
            text: col.name || D.emptyHeader,
          }),
        ),
      ),
    );
  }

  function renderActions(): void {
    const ok = dw.ready;
    copyButton.disabled = !ok;
    saveButton.disabled = !ok;
    actions.setAttribute("aria-busy", String(dw.making || dw.saving));
    const copiedTable = dw.feedback?.key === "tsv";
    const label = copyButton.querySelector("span:last-child");
    if (label) label.textContent = copiedTable && dw.feedback?.ok ? D.copied : D.copyTable;

    let text = "";
    if (dw.saving) text = D.saving;
    else if (dw.making) text = D.updating;
    else if (dw.feedback) text = dw.feedback.ok ? (dw.feedback.key === "tsv" ? D.tableCopied : D.copied) : D.copyFailed;
    else if (dw.savedName()) text = D.saved(dw.savedName() ?? "");
    status.textContent = text;
    status.classList.toggle("dw-status-ok", dw.feedback?.ok === true || (!!dw.savedName() && !dw.feedback));
    revealButton.hidden = !dw.savedName() || dw.feedback !== null || dw.making || dw.saving;

    const err = dw.error && dw.error.kind !== "analyse" ? dw.error : null;
    problem.hidden = !err;
    if (err) {
      replace(problem, createRunError(err.run));
    } else replace(problem);
    const w = warningsBlock(visibleWarnings({ warnings: dw.made?.warnings ?? [] }));
    warnings.hidden = !w || dw.made === null;
    replace(warnings, w);
  }

  function renderPreview(): void {
    const m = dw.made;
    preview.hidden = m === null;
    preview.classList.toggle("dw-stale", dw.making);
    preview.setAttribute("aria-busy", String(dw.making));
    if (!m) {
      madeKey = null;
      return;
    }
    if (m === madeKey) return;
    madeKey = m;
    const p = previewOf(m);
    previewCount.textContent = D.previewCount(p.rows.length, p.totalRows, p.header.length);
    const canRemove = dw.canRemoveColumn();
    const heads = p.header.map((name, j) => {
      const col = p.columns[j];
      const label = name || D.emptyHeader;
      const btn = h(
        "button",
        {
          type: "button",
          class: "dw-colbtn",
          disabled: !canRemove || !col,
          "aria-label": canRemove ? D.removeColumn(label) : `${label}. ${D.lastColumn}`,
          title: canRemove ? D.removeColumn(label) : D.lastColumn,
          onclick: () => {
            if (!col) return;
            pendingFocus = () => {
              const buttons = [...previewWrap.querySelectorAll<HTMLButtonElement>("th button:not(:disabled)")];
              (buttons[Math.min(j, buttons.length - 1)] ?? previewWrap).focus();
            };
            dw.removeColumn(col.index);
          },
        },
        h("span", { text: label }),
        icon("close", 14),
      );
      return h("th", { scope: "col", class: col?.numeric ? "dw-num" : "" }, btn);
    });
    const body = p.rows.map((row) => h("tr", {}, ...row.map((cell, j) => (j === 0 ? h("th", { scope: "row", class: "dw-rowhead", text: cell }) : h("td", { class: p.columns[j]?.numeric ? "dw-num" : "", text: cell })))));
    // Første kolonne er etiketten for raden; overskriften står likevel i kolonnen.
    replace(previewWrap, h("table", { class: "dw-table" }, h("caption", { class: "offscreen", text: D.previewCaption }), h("thead", {}, h("tr", {}, ...heads)), h("tbody", {}, ...body)));
  }

  function renderFields(): void {
    const m = dw.made;
    fieldsSection.hidden = m === null;
    for (const f of fieldRows) {
      const text = value(f.key);
      f.input.value = text === "" ? "" : text;
      f.input.placeholder = text === "" ? D.notFound : "";
      f.el.hidden = f.optional && text === "";
      f.button.disabled = text === "";
      const done = dw.feedback?.key === f.key;
      f.button.textContent = done ? (dw.feedback?.ok ? D.copied : D.copyFailed) : D.copy;
    }
  }

  function renderFailed(): void {
    const err = dw.error?.kind === "analyse" ? dw.error : null;
    if (!err) {
      replace(failed);
      return;
    }
    replace(
      failed,
      createRunError(err.run),
      h("p", { class: "help", text: D.failedHint }),
      h("div", { class: "button-row" }, h("button", { type: "button", class: "btn btn-primary", text: D.chooseOther, onclick: () => void dw.chooseFile() })),
    );
  }

  function render(): void {
    const phase = dw.phase;
    drop.hidden = phase !== "empty";
    drop.classList.toggle("dropzone-over", dragging);
    dropTitle.textContent = dragging ? S.dragging : texts.dropTitle;
    fileSection.hidden = phase === "empty";
    // På feilskjermen har feilkortet sin egen «Velg annen fil».
    otherFileButton.hidden = phase === "failed";
    fileName.textContent = dw.file ? c.displayName(dw.file) : "";
    reading.hidden = phase !== "analysing";
    failed.hidden = phase !== "failed";
    for (const b of readyBlocks) b.hidden = phase !== "ready";
    renderNotice();
    if (phase === "ready") {
      renderChoices();
      renderActions();
      renderPreview();
      renderFields();
      // Etter at en kolonne er klikket bort, havner fokus på nabokolonnen.
      pendingFocus?.();
      pendingFocus = null;
    } else {
      renderFailed();
    }
    if (lastPhase === "empty" && phase !== "empty") fileHeading.focus();
    if (lastPhase !== "empty" && phase === "empty") chooseButton.focus();
    lastPhase = phase;
  }

  let rendered = -1;
  const draw = () => {
    if (rendered === dw.version) return;
    rendered = dw.version;
    render();
  };
  dw.subscribe(draw);
  render();
  rendered = dw.version;

  return {
    el,
    update: draw,
    // Framdriften for en kort analyse sier ikke noe; «Leser filen …» holder.
    updateProgress() {},
    setDragging(over) {
      dragging = over;
      render();
    },
    focusResult() {},
  };
}
