// Transkribering sin del av Innstillinger: modeller, egen modellmappe og
// nøyaktighet/fart. Hører til verktøyet, ikke skallet (regel 6).

import { errorText } from "../../lib/errors";
import { formatBytes } from "../../lib/format";
import { modelDisplayName } from "../../lib/choices";
import { t } from "../../i18n/nb";
import { announce } from "../../ui/announce";
import { h, replace } from "../../ui/dom";
import { confirmDialog } from "../../ui/modal";
import { segmented } from "../../ui/segmented";
import type { CoreError, Decoding, ModelStatus } from "./api";
import type { ToolContext } from "../types";
import type { TranskriberingController } from "./controller";

const S = t.settings;

function modelTitle(m: ModelStatus): string {
  const size = S.models.size[m.size];
  const stil = S.models.stil[m.variant];
  return `${size} · ${stil}`;
}

export function mountSettingsSection(
  root: HTMLElement,
  c: TranskriberingController,
  _ctx: ToolContext,
): { refresh(): void } {
  // ---- modeller
  const total = h("p", { class: "help" });
  const list = h("ul", { class: "rows" });
  const modelError = h("div", { class: "card card-error", role: "alert", hidden: true });
  const modelsSection = h(
    "section",
    { class: "block", "aria-labelledby": "set-models" },
    h("h2", { id: "set-models", class: "block-title", text: S.models.title }),
    h("p", { class: "help", text: S.models.intro }),
    modelError,
    total,
    list,
  );

  // ---- egen modellmappe
  const folderState = h("p", { class: "path" });
  const appFolder = h("p", { class: "help path" });
  const folderMsg = h("p", { class: "info", role: "status", hidden: true });
  const folderError = h("div", { class: "card card-error", role: "alert", hidden: true });
  const resetButton = h("button", {
    type: "button",
    class: "btn",
    text: S.folder.reset,
    onclick: async () => showFolderResult(await c.setModelDir(null), S.folder.reset_done),
  });
  const folderSection = h(
    "section",
    { class: "block", "aria-labelledby": "set-folder" },
    h("h2", { id: "set-folder", class: "block-title", text: S.folder.title }),
    h("p", { class: "help", text: S.folder.intro }),
    folderState,
    appFolder,
    h(
      "div",
      { class: "button-row" },
      h("button", {
        type: "button",
        class: "btn",
        text: S.folder.choose,
        onclick: async () => {
          const r = await c.chooseModelDir();
          if (r !== "cancelled") showFolderResult(r, S.folder.saved);
        },
      }),
      resetButton,
    ),
    folderMsg,
    folderError,
  );

  function showFolderResult(err: CoreError | null, okText: string): void {
    folderError.hidden = true;
    folderMsg.hidden = true;
    if (err) {
      const e = errorText(err);
      folderError.hidden = false;
      replace(folderError, h("div", {}, h("p", { class: "card-strong", text: e.title }), h("p", { text: e.hint })));
    } else {
      folderMsg.hidden = false;
      folderMsg.textContent = okText;
    }
  }

  // ---- søkemåte
  const decodingSeg = segmented<Decoding>({
    legend: S.decoding.legend,
    options: [
      { value: "beam5", label: S.decoding.beam5 },
      { value: "greedy", label: S.decoding.greedy },
    ],
    value: c.decoding,
    onChange: (v) => void c.setDecoding(v),
    describedBy: "decoding-help",
  });
  const decodingHelp = h("p", { class: "help", id: "decoding-help" });
  const decodingSection = h(
    "section",
    { class: "block", "aria-labelledby": "set-decoding" },
    h("h2", { id: "set-decoding", class: "block-title", text: S.decoding.title }),
    h("p", { class: "help", text: S.decoding.intro }),
    decodingSeg.el,
    decodingHelp,
  );

  root.append(modelsSection, folderSection, decodingSection);

  function renderModels(): void {
    modelError.hidden = true;
    const models = c.models?.models ?? [];
    if (!c.models) {
      total.textContent = "";
      replace(list, h("li", { class: "empty", text: S.models.loadFailed }));
      return;
    }
    const shown = models.filter((m) => m.installed || m.partial_bytes > 0);
    const used = shown.reduce(
      (sum, m) => sum + (m.installed && m.location === "app" ? m.bytes : m.installed ? 0 : m.partial_bytes),
      0,
    );
    total.textContent = shown.length === 0 ? "" : S.models.total(formatBytes(used));
    if (shown.length === 0) {
      replace(list, h("li", { class: "empty", text: S.models.empty }));
      return;
    }
    replace(list, ...shown.map((m) => modelRow(m)));
  }

  function modelRow(m: ModelStatus): HTMLElement {
    const name = modelDisplayName(m);
    const own = m.installed && m.location === "custom";
    const where = !m.installed ? S.models.partial(formatBytes(m.partial_bytes)) : own ? S.models.inOwnFolder : S.models.inAppFolder;
    return h(
      "li",
      { class: "row" },
      h(
        "div",
        { class: "row-body" },
        h("p", { class: "row-name", text: modelTitle(m) }),
        h("p", { class: "row-status", text: `${name} · ${formatBytes(m.installed ? m.bytes : m.partial_bytes)}` }),
        h("p", { class: "row-hint", text: where }),
      ),
      h(
        "div",
        { class: "row-actions" },
        own
          ? h("p", { class: "row-hint", text: S.models.deleteBlocked })
          : h("button", {
              type: "button",
              class: "btn btn-danger-quiet",
              text: S.models.delete,
              "aria-label": S.models.deleteFile(`${modelTitle(m)} (${name})`),
              onclick: () => void remove(m),
            }),
      ),
    );
  }

  async function remove(m: ModelStatus): Promise<void> {
    const ok = await confirmDialog({
      title: S.models.confirmTitle,
      body: S.models.confirmBody(modelTitle(m), formatBytes(m.installed ? m.bytes : m.partial_bytes)),
      confirmLabel: S.models.confirmDelete,
      danger: true,
    });
    if (!ok) return;
    const err = await c.deleteModel(m.id);
    if (err) {
      const e = errorText(err);
      modelError.hidden = false;
      replace(modelError, h("div", {}, h("p", { class: "card-strong", text: e.title }), h("p", { text: e.hint })));
    } else {
      announce(S.models.deleted(modelTitle(m)));
    }
  }

  function renderFolder(): void {
    const custom = c.models?.custom_model_dir ?? null;
    folderState.textContent = custom ? S.folder.current(custom) : S.folder.none;
    appFolder.textContent = c.models ? S.folder.appFolder(c.models.app_model_dir) : "";
    resetButton.hidden = !custom;
  }

  function renderDecoding(): void {
    decodingSeg.set(c.decoding);
    decodingHelp.textContent = c.decoding === "beam5" ? S.decoding.beam5Hint : S.decoding.greedyHint;
  }

  function renderAll(): void {
    renderModels();
    renderFolder();
    renderDecoding();
  }

  c.subscribe((change) => {
    if (change.type === "models" || change.type === "decoding") renderAll();
  });
  renderAll();

  return {
    refresh() {
      folderMsg.hidden = true;
      folderError.hidden = true;
      void c.refreshModels();
    },
  };
}
