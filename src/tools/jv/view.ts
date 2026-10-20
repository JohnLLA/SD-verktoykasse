// Skjermen for ett jv-verktøy: tittel, og så enten nedlastingsskjermen eller
// den felles verktøyskjermen, ut fra om verktøyet er lastet ned.

import { t } from "../../i18n/nb";
import { h } from "../../ui/dom";
import type { ToolContext } from "../types";
import type { JvToolId } from "./api";
import type { JvChange, JvController } from "./controller";
import type { ToolSchema } from "./schema";
import type { ToolTexts } from "./texts";
import { createInstallView, type InstallView } from "./view-install";
import { createToolScreen, type ToolScreen } from "./view-screen";

export interface JvScreen {
  /** Skjermen vises: henter katalogen fra nett hvis verktøyet ikke er lastet ned. */
  onShow(): void;
  /** Filer sluppet i vinduet. */
  drop(paths: string[]): void;
  hover(over: boolean): void;
}

/** Lager skjermen for et verktøy som er lastet ned. Standard: `createToolScreen`. */
export type ScreenFactory = typeof createToolScreen;

export function mountJvTool(
  root: HTMLElement,
  c: JvController,
  id: JvToolId,
  schema: ToolSchema,
  texts: ToolTexts,
  ctx: ToolContext,
  createScreen: ScreenFactory = createToolScreen,
): JvScreen {
  const heading = h("h1", { class: "page-title", tabindex: -1, text: texts.name });
  const stage = h("div", { class: "stage" });
  root.append(heading, stage);

  let install: InstallView | null = null;
  let screen: ToolScreen | null = null;
  let shown: "install" | "screen" | null = null;
  let lastRunStatus = c.session(id).run.status;

  function show(kind: "install" | "screen"): void {
    if (shown === kind) return;
    shown = kind;
    if (kind === "install") {
      screen?.el.remove();
      install ??= createInstallView(c, id, texts);
      stage.append(install.el);
      install.update();
    } else {
      install?.el.remove();
      screen ??= createScreen(c, id, schema, texts, ctx.platform);
      stage.append(screen.el);
      screen.update();
    }
  }

  function refresh(change?: JvChange): void {
    const installed = c.isInstalled(id);
    show(installed ? "screen" : "install");
    if (change?.type === "install-progress" && change.id === id) install?.updateProgress();
    else if (change?.type === "run-progress" && change.id === id) screen?.updateProgress();
    else {
      if (installed) {
        screen?.update();
        const st = c.session(id).run.status;
        // Fokus til resultatet når en jobb er ferdig, så skjermleseren leser det.
        if (st !== lastRunStatus && (st === "done" || st === "failed")) window.setTimeout(() => screen?.focusResult(), 0);
        lastRunStatus = st;
      } else install?.update();
    }
  }

  c.subscribe((change) => {
    if ("id" in change && change.id !== id) return;
    refresh(change);
  });
  refresh();

  return {
    onShow() {
      refresh();
      void c.open(id);
    },
    drop(paths) {
      if (!c.isInstalled(id)) return;
      ctx.activate();
      c.addFiles(id, paths);
      const n = c.session(id).files.length;
      if (n > 0) ctx.announce(t.jv.screen.added(paths.length));
    },
    hover(over) {
      screen?.setDragging(over);
    },
  };
}
