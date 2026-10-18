// Én fil: venter, kjører (framdrift og tekst som fyller seg), feilet, avbrutt
// eller ferdig (tekst som kan rettes, avspilling, lagring).

import { errorText } from "../../lib/errors";
import { fileName } from "../../lib/files";
import { formatEta, formatPercent, formatTimecode } from "../../lib/format";
import { JobQueue, type QueueItem } from "../../lib/queue";
import { lastEndMs, segmentIndexAt } from "../../lib/segments";
import { SAVE_OPTIONS, type SaveKind } from "../../lib/export-request";
import { t } from "../../i18n/nb";
import type { Platform } from "../../platform/types";
import { announce } from "../../ui/announce";
import { h, nextId, replace } from "../../ui/dom";
import { icon } from "../../ui/icons";
import { confirmDialog } from "../../ui/modal";
import { progressBar, type ProgressBar } from "../../ui/progress";
import type { ControllerChange, TranskriberingController } from "./controller";
import { kvalitetLabel, malformLabel, stilLabel } from "./labels";

const T = t.transkribering;

export interface FileView {
  el: HTMLElement;
  onChange(change: ControllerChange): void;
  /** Rydder opp (stopper lyden) når visningen forlates. */
  destroy(): void;
  focusHeading(): void;
}

export function createFileView(c: TranskriberingController, platform: Platform, id: number): FileView {
  const first = c.queue.get(id);
  const body = h("div", { class: "file-body" });
  const heading = h("h2", { class: "file-title", tabindex: -1, text: first?.name ?? "" });
  const meta = h("p", { class: "file-meta" });
  const el = h(
    "div",
    { class: "view-file" },
    h(
      "div",
      { class: "file-head" },
      h(
        "button",
        { type: "button", class: "btn btn-quiet back", onclick: () => c.showNew() },
        icon("back", 18),
        h("span", { text: T.file.back }),
      ),
      heading,
      meta,
    ),
    body,
  );

  // Rester av den delen som er bygget for tilstanden akkurat nå.
  let signature = "";
  let progressRefs: { bar: ProgressBar; text: HTMLElement; cancel: HTMLButtonElement } | null = null;
  let liveList: HTMLElement | null = null;
  let liveBox: HTMLElement | null = null;
  let resultRefs: ResultRefs | null = null;
  let audio: HTMLAudioElement | null = null;

  function item(): QueueItem | undefined {
    return c.queue.get(id);
  }

  function sign(i: QueueItem): string {
    return `${i.state}|${i.cancelling}|${i.error?.code ?? ""}`;
  }

  function stopAudio(): void {
    if (audio) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      audio = null;
    }
  }

  function renderMeta(i: QueueItem): void {
    meta.textContent = i.choices
      ? T.file.meta(malformLabel(i.choices.malform), stilLabel(i.choices.stil), kvalitetLabel(i.choices.kvalitet))
      : "";
  }

  // ---- bygg innholdet for tilstanden

  function build(): void {
    const i = item();
    stopAudio();
    progressRefs = null;
    liveList = null;
    liveBox = null;
    resultRefs = null;
    if (!i) {
      replace(body);
      return;
    }
    heading.textContent = i.name;
    renderMeta(i);
    signature = sign(i);
    switch (i.state) {
      case "ready":
      case "queued":
      case "starting":
      case "running":
        buildWaitingOrRunning(i);
        break;
      case "done":
        buildResult(i);
        break;
      case "failed":
        buildFailed(i);
        break;
      case "cancelled":
        buildCancelled(i);
        break;
    }
  }

  function buildWaitingOrRunning(i: QueueItem): void {
    const running = i.state === "running" || i.state === "starting";
    const bar = progressBar(T.progress.label);
    const text = h("p", { class: "progress-text" });
    const cancel = h("button", {
      type: "button",
      class: "btn",
      text: t.common.cancel,
      onclick: () => c.cancelItem(id),
    });
    progressRefs = { bar, text, cancel };
    liveList = h("ol", { class: "segments segments-live" });
    liveBox = h("div", { class: "live-box", tabindex: 0, role: "region", "aria-label": T.file.liveTitle }, liveList);
    replace(
      body,
      h(
        "section",
        { class: "card card-progress", "aria-label": T.progress.label },
        h("div", { class: "card-body" }, bar.el, text, running && h("p", { class: "card-sub", text: T.progress.keepOpen })),
        cancel,
      ),
      running &&
        h(
          "section",
          { class: "block" },
          h("h3", { class: "block-title", text: T.file.liveTitle }),
          liveBox,
          h("p", { class: "live-empty", text: T.file.liveEmpty }),
        ),
    );
    for (let n = 0; n < i.segments.length; n++) appendLive(i, n);
    updateProgress(i);
  }

  function updateProgress(i: QueueItem): void {
    if (!progressRefs) return;
    const { bar, text, cancel } = progressRefs;
    let line: string;
    if (i.state === "queued" || i.state === "ready") line = T.queue.status.waiting;
    else if (i.cancelling) line = T.progress.cancelling;
    else if (i.state === "starting" || (i.percent === 0 && i.etaMs === null)) line = T.progress.verifying;
    else line = `${formatPercent(i.percent)} · ${formatEta(i.etaMs)}`;
    bar.set(i.state === "queued" || i.state === "ready" ? 0 : i.percent, line);
    text.textContent = line;
    cancel.disabled = i.cancelling;
  }

  function appendLive(i: QueueItem, index: number): void {
    if (!liveList || !liveBox) return;
    const seg = i.segments[index];
    if (!seg) return;
    const box = liveBox;
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    liveList.append(
      h(
        "li",
        { class: "seg" },
        h("span", { class: "time time-static", text: formatTimecode(seg.start_ms) }),
        h("p", { class: "seg-text", text: seg.text }),
      ),
    );
    box.parentElement?.classList.add("has-live");
    if (nearBottom) box.scrollTop = box.scrollHeight;
  }

  function buildFailed(i: QueueItem): void {
    const e = errorText(i.error ?? { code: "internal" });
    replace(
      body,
      h(
        "div",
        { class: "card card-error", role: "alert" },
        icon("alert", 28),
        h(
          "div",
          { class: "card-body" },
          h("p", { class: "card-title", text: T.file.failedTitle }),
          h("p", { class: "card-strong", text: e.title }),
          e.hint && h("p", { text: e.hint }),
          h(
            "div",
            { class: "card-actions" },
            i.error?.code !== "unsupported_format" &&
              h("button", { type: "button", class: "btn btn-primary", text: t.common.retry, onclick: () => c.retry(id) }),
            h("button", { type: "button", class: "btn", text: t.common.remove, onclick: () => c.removeItem(id) }),
          ),
        ),
      ),
    );
  }

  function buildCancelled(_i: QueueItem): void {
    replace(
      body,
      h(
        "div",
        { class: "card", role: "status" },
        icon("info", 28),
        h(
          "div",
          { class: "card-body" },
          h("p", { class: "card-title", text: T.file.cancelledTitle }),
          h("p", { text: T.file.cancelledHint }),
          h(
            "div",
            { class: "card-actions" },
            h("button", { type: "button", class: "btn btn-primary", text: T.file.restart, onclick: () => c.retry(id) }),
            h("button", { type: "button", class: "btn", text: t.common.remove, onclick: () => c.removeItem(id) }),
          ),
        ),
      ),
    );
  }

  // ---- resultat

  interface ResultRefs {
    status: HTMLElement;
    error: HTMLElement;
    rows: HTMLElement[];
    playbackNote: HTMLElement;
  }

  function buildResult(i: QueueItem): void {
    if (i.segments.length === 0) {
      replace(
        body,
        h(
          "div",
          { class: "card", role: "status" },
          icon("info", 28),
          h(
            "div",
            { class: "card-body" },
            h("p", { class: "card-title", text: T.file.noSpeechTitle }),
            h("p", { text: T.file.noSpeechHint }),
            h("div", { class: "card-actions" }, h("button", { type: "button", class: "btn", text: t.common.remove, onclick: () => c.removeItem(id) })),
          ),
        ),
      );
      return;
    }

    const withHours = lastEndMs(i.segments) >= 3_600_000;
    const status = h("p", { class: "status-line", role: "status" });
    const error = h("div", { class: "card card-error", role: "alert", hidden: true });
    const playbackNote = h("p", { class: "warn", role: "status", hidden: true, text: T.result.playbackFailed });
    const revealLabel = T.result.reveal[platform.os];

    const toolbar = h(
      "div",
      { class: "toolbar", role: "toolbar", "aria-label": T.result.title },
      h(
        "button",
        { type: "button", class: "btn btn-primary", onclick: () => openSaveDialog() },
        icon("save", 18),
        h("span", { text: T.result.saveAs }),
      ),
      h(
        "button",
        {
          type: "button",
          class: "btn",
          onclick: async () => {
            const ok = await c.copyAll(id);
            announce(ok ? T.result.copied : T.result.copyFailed);
          },
        },
        icon("copy", 18),
        h("span", { text: T.result.copyAll }),
      ),
      h(
        "button",
        { type: "button", class: "btn", onclick: () => void c.reveal(id) },
        icon("folder", 18),
        h("span", { text: revealLabel }),
      ),
    );

    audio = h("audio", { class: "player", controls: true, preload: "metadata", "aria-label": T.result.player });
    const a = audio;
    let playable = false;
    a.addEventListener("error", () => {
      playable = false;
      playbackNote.hidden = false;
    });
    void platform.playbackUrl(i.path).then((url) => {
      if (audio !== a) return; // visningen er forlatt
      if (url) {
        playable = true;
        a.src = url;
      } else {
        playbackNote.hidden = false;
      }
    });

    const list = h("ol", { class: "segments segments-result" });
    const rows: HTMLElement[] = [];
    i.segments.forEach((seg, index) => {
      const time = formatTimecode(seg.start_ms, withHours);
      const text = h("div", {
        class: "seg-text seg-edit",
        role: "textbox",
        "aria-multiline": "false",
        "aria-label": T.result.segmentText(time),
        spellcheck: "true",
        lang: "nb",
        text: seg.text,
      });
      text.setAttribute("contenteditable", "plaintext-only");
      if (text.contentEditable !== "plaintext-only") text.setAttribute("contenteditable", "true");
      text.addEventListener("input", () => c.edit(id, index, text.textContent ?? ""));
      text.addEventListener("blur", () => {
        const current = item()?.segments[index]?.text;
        if (current !== undefined && text.textContent !== current) text.textContent = current;
      });
      text.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          (rows[index + 1]?.querySelector(".seg-edit") as HTMLElement | null)?.focus();
        }
      });
      text.addEventListener("paste", (e) => {
        e.preventDefault();
        const pasted = e.clipboardData?.getData("text/plain") ?? "";
        document.execCommand("insertText", false, pasted.replace(/\s+/g, " "));
      });
      const row = h(
        "li",
        { class: "seg" },
        h("button", {
          type: "button",
          class: "time",
          text: time,
          "aria-label": T.result.segmentTime(time),
          onclick: () => {
            if (!playable) {
              playbackNote.hidden = false;
              return;
            }
            a.currentTime = seg.start_ms / 1000;
            void a.play().catch(() => {
              playbackNote.hidden = false;
            });
          },
        }),
        text,
      );
      rows.push(row);
      list.append(row);
    });

    // Fremhev segmentet som spilles nå.
    let lastIndex = -1;
    a.addEventListener("timeupdate", () => {
      const now = item()?.segments ?? [];
      const idx = segmentIndexAt(now, a.currentTime * 1000);
      if (idx === lastIndex) return;
      rows[lastIndex]?.classList.remove("seg-playing");
      rows[lastIndex]?.removeAttribute("aria-current");
      lastIndex = idx;
      const row = rows[idx];
      if (row) {
        row.classList.add("seg-playing");
        row.setAttribute("aria-current", "true");
        if (!a.paused) row.scrollIntoView({ block: "nearest" });
      }
    });

    resultRefs = { status, error, rows, playbackNote };
    replace(
      body,
      toolbar,
      status,
      error,
      h("div", { class: "player-bar" }, a),
      playbackNote,
      h("p", { class: "help", text: T.result.hint }),
      list,
    );
    renderStatus(i);
  }

  function renderStatus(i: QueueItem): void {
    if (!resultRefs) return;
    const { status } = resultRefs;
    if (i.savedPath) {
      const saved = T.result.saved(fileName(i.savedPath));
      status.textContent = JobQueue.isDirty(i) ? `${saved} ${T.result.edited}` : saved;
    } else {
      status.textContent = "";
    }
  }

  function showSaveError(e: { title: string; hint: string }): void {
    if (!resultRefs) return;
    const box = resultRefs.error;
    box.hidden = false;
    replace(
      box,
      icon("alert", 24),
      h("div", {}, h("p", { class: "card-title", text: T.result.saveFailed }), h("p", { class: "card-strong", text: e.title }), e.hint && h("p", { text: e.hint })),
    );
  }

  async function doSave(kind: SaveKind, opts: { chooseLocation?: boolean; overwrite?: boolean }): Promise<void> {
    if (resultRefs) resultRefs.error.hidden = true;
    const r = await c.save(id, kind, opts);
    const i = item();
    switch (r.status) {
      case "saved":
        if (i) renderStatus(i);
        announce(T.result.saved(fileName(r.path)));
        break;
      case "exists": {
        const ok = await confirmDialog({
          title: T.save.overwriteTitle,
          body: T.save.overwriteBody(r.name),
          confirmLabel: T.save.overwriteConfirm,
          danger: true,
        });
        if (ok) await doSave(kind, { ...opts, overwrite: true });
        break;
      }
      case "failed":
        showSaveError(errorText(r.error));
        break;
      case "cancelled":
        break;
    }
  }

  function openSaveDialog(): void {
    const previous = document.activeElement as HTMLElement | null;
    const titleId = nextId("save-title");
    const checkId = nextId("save-place");
    const choose = h("input", { type: "checkbox", id: checkId });
    const buttons = SAVE_OPTIONS.map((o) => {
      const f = T.save.formats[o.kind];
      return h(
        "button",
        {
          type: "button",
          class: "save-option",
          onclick: () => {
            const chooseLocation = choose.checked;
            dialog.close();
            void doSave(o.kind, { chooseLocation });
          },
        },
        h("span", { class: "save-label", text: f.label }),
        h("span", { class: "save-ext", text: f.hint ? `${f.ext} · ${f.hint}` : f.ext }),
      );
    });
    const dialog = h(
      "dialog",
      { class: "modal modal-save", "aria-labelledby": titleId },
      h("h2", { id: titleId, text: T.save.title }),
      h("div", { class: "save-list" }, ...buttons),
      h("div", { class: "check" }, choose, h("label", { for: checkId, text: T.save.choosePlace })),
      h("div", { class: "modal-actions" }, h("button", { type: "button", class: "btn", text: t.common.close, onclick: () => dialog.close() })),
    );
    dialog.addEventListener("close", () => {
      dialog.remove();
      previous?.focus();
    });
    document.body.append(dialog);
    dialog.showModal();
    buttons[0]?.focus();
  }

  build();

  return {
    el,
    focusHeading: () => heading.focus(),
    destroy: stopAudio,
    onChange(change) {
      const i = item();
      if (!i) {
        c.showNew();
        return;
      }
      switch (change.type) {
        case "items":
          if (sign(i) !== signature) build();
          else if (progressRefs) updateProgress(i);
          break;
        case "progress":
          if (change.id === id) updateProgress(i);
          break;
        case "segment":
          if (change.id === id) appendLive(i, change.index);
          break;
        case "edit":
          if (change.id === id) renderStatus(i);
          break;
        default:
          break;
      }
    },
  };
}
