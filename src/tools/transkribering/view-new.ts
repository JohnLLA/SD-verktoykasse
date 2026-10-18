// «Ny transkribering»: slippsone, filer som venter, de tre valgene, start eller
// nedlasting av modell, og listen over filer som er i gang eller ferdige.
// Delene bygges én gang og oppdateres på stedet, så framdrift og nedlasting
// ikke får skjermen til å blinke eller fokus til å hoppe.

import { errorText } from "../../lib/errors";
import { formatBytes, formatEta, formatPercent } from "../../lib/format";
import { lowMemoryForBest, modelDisplayName, KVALITETER, MALFORMS, STILER } from "../../lib/choices";
import { JobQueue, type QueueItem } from "../../lib/queue";
import { t } from "../../i18n/nb";
import { h, replace } from "../../ui/dom";
import { icon } from "../../ui/icons";
import { progressBar, type ProgressBar } from "../../ui/progress";
import { segmented, type Segmented } from "../../ui/segmented";
import { confirmDialog } from "../../ui/modal";
import type { ControllerChange, TranskriberingController } from "./controller";
import { kvalitetLabel, malformLabel, stilLabel } from "./labels";

const T = t.transkribering;

export interface NewView {
  el: HTMLElement;
  /** Filer dras over vinduet. */
  setDragging(over: boolean): void;
  onChange(change: ControllerChange): void;
}

export function createNewView(c: TranskriberingController): NewView {
  // ---- filer i gang eller ferdige
  const queueList = h("ul", { class: "rows" });
  const queueSection = h(
    "section",
    { class: "block", "aria-labelledby": "queue-title" },
    h("h2", { id: "queue-title", class: "block-title", text: T.queue.title }),
    queueList,
  );
  const rowRefs = new Map<number, RowRefs>();

  // ---- slippsone
  const dropTitle = h("p", { class: "drop-title" });
  const dropButton = h("button", { type: "button", class: "btn btn-primary btn-large", onclick: () => void c.chooseFiles() });
  const drop = h(
    "div",
    {
      class: "dropzone",
      onclick: (e: Event) => {
        if (!(e.target as HTMLElement).closest("button")) void c.chooseFiles();
      },
    },
    icon("upload", 40),
    dropTitle,
    h("p", { class: "drop-or", text: T.drop.or }),
    dropButton,
    h("p", { class: "drop-formats", text: T.drop.formats }),
  );
  let dragging = false;

  // ---- klare filer
  const readyList = h("ul", { class: "ready-list" });
  const readySection = h(
    "section",
    { class: "block", "aria-labelledby": "ready-title" },
    h("h2", { id: "ready-title", class: "block-title", text: T.readyTitle }),
    readyList,
  );

  // ---- valg
  const stilHelpL = h("span", { class: "help-lydrett", text: T.choices.stil.explainLydrett });
  const stilHelpT = h("span", { class: "help-tolket", text: T.choices.stil.explainTolket });
  const stilHelp = h("p", { class: "help", id: "stil-help" }, stilHelpL, stilHelpT);
  const kvalitetHelp = h("p", { class: "help", id: "kvalitet-help" });
  const memoryWarning = h("p", { class: "warn", role: "status" });

  const malformSeg: Segmented<(typeof MALFORMS)[number]> = segmented({
    legend: T.choices.malform.legend,
    options: MALFORMS.map((value) => ({ value, label: malformLabel(value) })),
    value: c.choices.malform,
    onChange: (v) => void c.setChoice("malform", v),
  });
  const stilSeg = segmented({
    legend: T.choices.stil.legend,
    options: STILER.map((value) => ({ value, label: stilLabel(value) })),
    value: c.choices.stil,
    onChange: (v) => void c.setChoice("stil", v),
    describedBy: "stil-help",
  });
  const kvalitetSeg = segmented({
    legend: T.choices.kvalitet.legend,
    options: KVALITETER.map((value) => ({ value, label: kvalitetLabel(value) })),
    value: c.choices.kvalitet,
    onChange: (v) => void c.setChoice("kvalitet", v),
    describedBy: "kvalitet-help",
  });
  const choices = h(
    "section",
    { class: "block choices", "aria-labelledby": "choices-title" },
    h("h2", { id: "choices-title", class: "block-title", text: T.choices.title }),
    h(
      "div",
      { class: "choice-grid" },
      h("div", { class: "choice" }, malformSeg.el),
      h("div", { class: "choice" }, stilSeg.el, stilHelp),
      h("div", { class: "choice" }, kvalitetSeg.el, kvalitetHelp, memoryWarning),
    ),
  );

  // ---- start eller modell
  const action = h("div", { class: "action" });
  let actionKey = "";
  let downloadBar: ProgressBar | null = null;
  let downloadText: HTMLElement | null = null;

  const el = h("div", { class: "view-new" }, queueSection, drop, readySection, choices, action);

  // ---- tegning

  function renderDrop(): void {
    const compact = c.queue.items.length > 0;
    drop.classList.toggle("dropzone-compact", compact);
    drop.classList.toggle("dropzone-over", dragging);
    dropTitle.textContent = dragging ? T.drop.dragging : compact ? T.drop.chooseMore : T.drop.title;
    dropButton.textContent = T.drop.choose;
  }

  function renderReady(): void {
    const ready = c.queue.ready();
    readySection.hidden = ready.length === 0;
    replace(
      readyList,
      ...ready.map((item) =>
        h(
          "li",
          { class: "ready-item" },
          icon("file", 20),
          h("span", { class: "ready-name", text: item.name }),
          h(
            "button",
            {
              type: "button",
              class: "btn btn-icon",
              "aria-label": T.readyRemove(item.name),
              title: t.common.remove,
              onclick: () => c.removeItem(item.id),
            },
            icon("close", 18),
          ),
        ),
      ),
    );
  }

  function renderQueue(): void {
    const items = c.queue.items.filter((i) => i.state !== "ready");
    queueSection.hidden = items.length === 0;
    rowRefs.clear();
    replace(queueList, ...items.map((item) => row(item)));
  }

  function renderChoices(): void {
    malformSeg.set(c.choices.malform);
    stilSeg.set(c.choices.stil);
    kvalitetSeg.set(c.choices.kvalitet);
    stilHelp.classList.toggle("help-lydrett-on", c.choices.stil === "lydrett");
    stilHelp.classList.toggle("help-tolket-on", c.choices.stil === "tolket");
    kvalitetHelp.textContent = T.choices.kvalitet.hint[c.choices.kvalitet];
    const gb = lowMemoryForBest(c.totalMemoryBytes, c.choices.kvalitet);
    memoryWarning.textContent = gb === null ? "" : T.choices.kvalitet.lowMemory(gb);
    memoryWarning.hidden = gb === null;
  }

  /** Nøkkel som endres når handlingsfeltet må bygges på nytt (ikke ved framdrift). */
  function computeActionKey(): string {
    const need = c.modelNeed();
    const d = c.download;
    return [
      c.cpuSupported,
      c.queue.ready().length,
      c.modelsError?.code ?? "",
      need?.model.id ?? "",
      need?.installed ?? "",
      need?.partialBytes ? "partial" : "",
      d?.status ?? "",
      d?.error?.code ?? "",
    ].join("|");
  }

  function renderAction(): void {
    const key = computeActionKey();
    if (key !== actionKey) {
      actionKey = key;
      buildAction();
    }
    updateDownloadProgress();
  }

  function buildAction(): void {
    downloadBar = null;
    downloadText = null;
    const ready = c.queue.ready();
    if (ready.length === 0) {
      action.hidden = true;
      replace(action);
      return;
    }
    action.hidden = false;

    if (!c.cpuSupported) {
      replace(
        action,
        h(
          "div",
          { class: "card card-error", role: "alert" },
          icon("alert", 24),
          h(
            "div",
            {},
            h("p", { class: "card-title", text: T.system.cpuUnsupportedTitle }),
            h("p", { text: T.system.cpuUnsupportedHint(c.system?.missing_cpu_features ?? []) }),
          ),
        ),
      );
      return;
    }

    const need = c.modelNeed();
    if (!need) {
      replace(
        action,
        h(
          "div",
          { class: "card card-error", role: "alert" },
          icon("alert", 24),
          h(
            "div",
            {},
            h("p", { class: "card-title", text: T.model.downloadFailed }),
            h("p", { text: errorText(c.modelsError ?? { code: "internal" }).hint }),
            h("button", { type: "button", class: "btn", text: t.common.retry, onclick: () => void c.refreshModels() }),
          ),
        ),
      );
      return;
    }

    if (need.installed) {
      replace(
        action,
        h("button", {
          type: "button",
          class: "btn btn-primary btn-large btn-start",
          text: ready.length > 1 ? T.start.buttonMany(ready.length) : T.start.button,
          onclick: () => c.start(),
        }),
      );
      return;
    }

    const d = c.download;
    if (d && (d.status === "starting" || d.status === "active")) {
      downloadBar = progressBar(T.model.downloading);
      downloadText = h("p", { class: "card-sub" });
      replace(
        action,
        h(
          "div",
          { class: "card" },
          icon("download", 24),
          h(
            "div",
            { class: "card-body" },
            h("p", { class: "card-title", text: T.model.downloading }),
            h("p", { class: "card-sub", text: T.model.name(modelDisplayName(need.model)) }),
            downloadBar.el,
            downloadText,
          ),
          h("button", { type: "button", class: "btn", text: T.model.cancelDownload, onclick: () => c.cancelDownload() }),
        ),
      );
      return;
    }

    const failed = d?.status === "failed" && d.error ? errorText(d.error) : null;
    replace(
      action,
      failed &&
        h(
          "div",
          { class: "card card-error", role: "alert" },
          icon("alert", 24),
          h("div", {}, h("p", { class: "card-title", text: failed.title }), h("p", { text: failed.hint })),
        ),
      d?.status === "cancelled" && h("p", { class: "info", role: "status", text: T.model.downloadCancelled }),
      h(
        "div",
        { class: "card" },
        icon("download", 24),
        h(
          "div",
          { class: "card-body" },
          h("p", { class: "card-title", text: T.model.needs(formatBytes(need.model.bytes)) }),
          h("p", { class: "card-sub", text: T.model.name(modelDisplayName(need.model)) }),
          need.partialBytes > 0 && h("p", { class: "card-sub", text: T.model.resumeInfo(formatBytes(need.partialBytes)) }),
          h("p", { class: "card-sub", text: T.model.onlineNote }),
        ),
        h("button", {
          type: "button",
          class: "btn btn-primary btn-large",
          text: T.model.download,
          onclick: () => void c.downloadModel(),
        }),
      ),
    );
  }

  function updateDownloadProgress(): void {
    const d = c.download;
    if (!d || !downloadBar || !downloadText) return;
    if (d.total > 0) {
      const pct = (d.downloaded / d.total) * 100;
      downloadBar.set(pct, formatPercent(pct));
      downloadText.textContent = `${T.model.progress(formatBytes(d.downloaded), formatBytes(d.total))} · ${formatPercent(pct)}`;
    } else {
      downloadBar.set(null);
      downloadText.textContent = "";
    }
  }

  // ---- rader i listen over filer

  interface RowRefs {
    status: HTMLElement;
    bar: ProgressBar | null;
  }

  function statusText(item: QueueItem): string {
    switch (item.state) {
      case "queued":
        return T.queue.status.waiting;
      case "starting":
        return item.cancelling ? T.progress.cancelling : T.queue.status.starting;
      case "running":
        if (item.cancelling) return T.progress.cancelling;
        return item.percent === 0 && item.etaMs === null
          ? T.progress.verifying
          : `${formatPercent(item.percent)} · ${formatEta(item.etaMs)}`;
      case "done":
        return T.queue.status.done;
      case "cancelled":
        return T.queue.status.cancelled;
      default:
        return T.queue.status.failed;
    }
  }

  function row(item: QueueItem): HTMLElement {
    const active = item.state === "running" || item.state === "starting";
    const bar = active ? progressBar(T.progress.label) : null;
    const status = h("p", { class: "row-status", text: statusText(item) });
    if (bar) bar.set(item.percent, status.textContent ?? "");
    rowRefs.set(item.id, { status, bar });

    const err = item.state === "failed" && item.error ? errorText(item.error) : null;
    const canOpen = item.state !== "failed" && item.state !== "cancelled" && item.state !== "queued";
    const name = canOpen
      ? h("button", {
          type: "button",
          class: "link row-name",
          text: item.name,
          "aria-label": T.queue.open(item.name),
          onclick: () => c.openFile(item.id),
        })
      : h("span", { class: "row-name", text: item.name });

    const actions: HTMLElement[] = [];
    if (item.state === "queued" || active) {
      actions.push(
        h("button", {
          type: "button",
          class: "btn",
          text: T.queue.cancel,
          disabled: item.cancelling,
          "aria-label": T.queue.cancelFile(item.name),
          onclick: () => c.cancelItem(item.id),
        }),
      );
    }
    if (item.state === "done") {
      actions.push(h("button", { type: "button", class: "btn", text: t.common.open, "aria-label": T.queue.open(item.name), onclick: () => c.openFile(item.id) }));
    }
    if ((item.state === "failed" && item.error?.code !== "unsupported_format") || item.state === "cancelled") {
      actions.push(h("button", { type: "button", class: "btn", text: t.common.retry, onclick: () => c.retry(item.id) }));
    }
    if (item.state === "done" || item.state === "failed" || item.state === "cancelled") {
      actions.push(
        h("button", {
          type: "button",
          class: "btn btn-quiet",
          text: t.common.remove,
          "aria-label": T.queue.removeFile(item.name),
          onclick: () => void removeWithConfirm(item),
        }),
      );
    }

    const stateIcon =
      item.state === "done" ? icon("check", 22) : item.state === "failed" ? icon("alert", 22) : icon("file", 22);
    return h(
      "li",
      { class: `row row-${item.state}` },
      stateIcon,
      h(
        "div",
        { class: "row-body" },
        name,
        err ? h("p", { class: "row-status row-error", role: "alert", text: err.title }) : status,
        err && h("p", { class: "row-hint", text: err.hint }),
        bar?.el,
      ),
      h("div", { class: "row-actions" }, ...actions),
    );
  }

  async function removeWithConfirm(item: QueueItem): Promise<void> {
    if (JobQueue.isDirty(item)) {
      const ok = await confirmDialog({
        title: T.queue.confirmRemoveTitle,
        body: T.queue.confirmRemoveBody,
        confirmLabel: T.queue.confirmRemove,
        danger: true,
      });
      if (!ok) return;
    }
    c.removeItem(item.id);
  }

  function updateRowProgress(id: number): void {
    const item = c.queue.get(id);
    const refs = rowRefs.get(id);
    if (!item || !refs) return;
    const text = statusText(item);
    refs.status.textContent = text;
    refs.bar?.set(item.percent, text);
  }

  function renderAll(): void {
    renderDrop();
    renderReady();
    renderQueue();
    renderChoices();
    renderAction();
  }

  renderAll();

  return {
    el,
    setDragging(over) {
      dragging = over;
      renderDrop();
    },
    onChange(change) {
      switch (change.type) {
        case "progress":
          updateRowProgress(change.id);
          break;
        case "segment":
        case "edit":
          break;
        case "items":
        case "screen":
          renderDrop();
          renderReady();
          renderQueue();
          renderAction();
          break;
        case "choices":
          renderChoices();
          renderAction();
          break;
        case "models":
        case "system":
          renderChoices();
          renderAction();
          break;
        case "download":
          renderAction();
          break;
        case "decoding":
          break;
      }
    },
  };
}
